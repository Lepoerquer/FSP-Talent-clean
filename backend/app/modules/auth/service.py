from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

try:
    from backend.app.core.config import settings
    from backend.app.core.database import get_db
    from backend.app.core.security import (
        create_access_token,
        decode_access_token,
        get_password_hash,
        verify_password,
    )
    from backend.app.models.candidate import CandidateProfile
    from backend.app.models.company import Company, EmployerMember
    from backend.app.models.invitation import AuditLog
    from backend.app.models.user import Consent, User
    from backend.app.modules.auth.schemas import (
        RegisterRequest,
        TokenResponse,
        UserRole,
    )
except ImportError:
    from app.core.config import settings
    from app.core.database import get_db
    from app.core.security import (
        create_access_token,
        decode_access_token,
        get_password_hash,
        verify_password,
    )
    from app.models.candidate import CandidateProfile
    from app.models.company import Company, EmployerMember
    from app.models.invitation import AuditLog
    from app.models.user import Consent, User
    from app.modules.auth.schemas import RegisterRequest, TokenResponse, UserRole

security_scheme = HTTPBearer(auto_error=False)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def register_user(db: Session, req: RegisterRequest) -> User:
    if not req.consent_personal_data:
        # 152-FZ: personal data is not processed without the subject's consent
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Без согласия на обработку персональных данных регистрация невозможна (152-ФЗ).",
        )
    email_clean = req.email.lower().strip()
    existing = get_user_by_email(db, email_clean)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже зарегистрирован в системе.",
        )

    # 1. Create base User
    user = User(
        email=email_clean,
        hashed_password=get_password_hash(req.password),
        role=req.role.value,
        is_active=True,
        email_verified=False,
    )
    db.add(user)
    db.flush()

    now = datetime.now(timezone.utc)

    # 2. Record 152-FZ Consents
    if req.consent_personal_data:
        c1 = Consent(
            user_id=user.id,
            consent_type="PERSONAL_DATA",
            version="1.0",
            is_given=True,
            given_at=now,
        )
        db.add(c1)

    if req.consent_profile_distribution and req.role == UserRole.CANDIDATE:
        c2 = Consent(
            user_id=user.id,
            consent_type="PROFILE_DISTRIBUTION",
            version="1.0",
            is_given=True,
            given_at=now,
        )
        db.add(c2)

    # 3. Create role-specific entity
    if req.role == UserRole.CANDIDATE:
        cand_profile = CandidateProfile(
            user_id=user.id,
            first_name=req.first_name,
            last_name=req.last_name,
            fsp_id=req.fsp_id,
            status="ACTIVELY_SEARCHING",
            hide_contacts_globally=True,
            # a typed-in FSP ID is only a claim: achievements are verified by linking through the registry
            is_fsp_verified=False,
        )
        db.add(cand_profile)

    elif req.role == UserRole.EMPLOYER:
        company_name = req.company_name or f"Компания ({user.email})"
        company = Company(
            name=company_name,
            is_verified=False,
        )
        db.add(company)
        db.flush()

        member = EmployerMember(
            user_id=user.id,
            company_id=company.id,
            role="OWNER",
        )
        db.add(member)

    # 4. Audit Log
    audit = AuditLog(
        user_id=user.id,
        action="USER_REGISTERED",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "role": user.role},
    )
    db.add(audit)

    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учетная запись заблокирована.",
        )
    return user


def create_auth_token(user: User, db: Session) -> TokenResponse:
    # Resolve fsp_id if candidate
    fsp_id = None
    if user.candidate_profile and user.candidate_profile.fsp_id:
        fsp_id = user.candidate_profile.fsp_id

    access_token = create_access_token(
        subject=user.id,
        role=user.role,
        email=user.email,
        fsp_id=fsp_id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        email=user.email,
        role=user.role,
        fsp_id=fsp_id,
        email_verified=user.email_verified,
    )


def verify_email_simulation(db: Session, email: str) -> User:
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь с указанным email не найден.",
        )
    user.email_verified = True
    
    audit = AuditLog(
        user_id=user.id,
        action="EMAIL_VERIFIED_SIMULATION",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email},
    )
    db.add(audit)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not auth_header or not auth_header.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не предоставлен токен авторизации (Bearer token).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(auth_header.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истекший токен доступа.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректная структура токена.",
        )

    user = get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или деактивирован.",
        )

    return user


def require_role(allowed_roles: list[str]):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостаточно прав. Требуется одна из ролей: {', '.join(allowed_roles)}.",
            )
        return current_user
    return role_checker


def require_candidate(current_user: User = Depends(require_role(["CANDIDATE"]))) -> User:
    return current_user


def require_employer(current_user: User = Depends(require_role(["EMPLOYER"]))) -> User:
    return current_user


def require_admin(current_user: User = Depends(require_role(["ADMIN"]))) -> User:
    return current_user


def get_optional_user(
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """The signed-in user, or None for an anonymous request. An invalid token is still rejected."""
    if not auth_header or not auth_header.credentials:
        return None
    return get_current_user(auth_header, db)


def get_current_candidate(
    current_user: User = Depends(require_candidate),
    db: Session = Depends(get_db),
) -> CandidateProfile:
    """The candidate profile of the signed-in user: a candidate only ever acts on their own data."""
    profile = db.query(CandidateProfile).filter(CandidateProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANDIDATE_PROFILE_NOT_FOUND", "message": "Профиль кандидата не найден."},
        )
    return profile


def get_current_company(
    current_user: User = Depends(require_employer),
    db: Session = Depends(get_db),
) -> Company:
    """The company of the signed-in employer: an employer only ever acts on behalf of their own company."""
    member = db.query(EmployerMember).filter(EmployerMember.user_id == current_user.id).first()
    if not member or not member.company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "COMPANY_NOT_FOUND", "message": "Компания работодателя не найдена."},
        )
    return member.company
