from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

try:
    from backend.app.core.database import get_db
    from backend.app.models.user import User
    from backend.app.modules.auth import service
    from backend.app.modules.auth.schemas import (
        LoginRequest,
        RegisterRequest,
        TokenResponse,
        UserResponse,
        VerifyEmailRequest,
    )
except ImportError:
    from app.core.database import get_db
    from app.models.user import User
    from app.modules.auth import service
    from app.modules.auth.schemas import (
        LoginRequest,
        RegisterRequest,
        TokenResponse,
        UserResponse,
        VerifyEmailRequest,
    )

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user (CANDIDATE, EMPLOYER) with 152-FZ consents and issue access token."""
    user = service.register_user(db, req)
    return service.create_auth_token(user, db)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email and password, issuing JWT access token with role and FSP claims."""
    user = service.authenticate_user(db, req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный адрес электронной почты или пароль.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return service.create_auth_token(user, db)


@router.post("/verify-email", response_model=UserResponse)
def verify_email(
    req: VerifyEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(service.get_current_user),
):
    """Simulate email verification for testing and fast UX onboarding (the demo code is 123456).

    Only the signed-in user's own address can be confirmed.
    """
    if req.email and req.email.lower().strip() != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Можно подтвердить только адрес своей учётной записи.",
        )
    if req.code != '123456':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный код подтверждения. На демонстрационном стенде используйте код 123456.",
        )
    updated_user = service.verify_email_simulation(db, current_user.email)
    
    fsp_id = None
    if updated_user.candidate_profile and updated_user.candidate_profile.fsp_id:
        fsp_id = updated_user.candidate_profile.fsp_id

    return UserResponse(
        id=updated_user.id,
        email=updated_user.email,
        role=updated_user.role,
        is_active=updated_user.is_active,
        email_verified=updated_user.email_verified,
        fsp_id=fsp_id,
        created_at=updated_user.created_at,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(service.get_current_user)):
    """Get the current authenticated user's profile and active roles."""
    fsp_id = None
    if current_user.candidate_profile and current_user.candidate_profile.fsp_id:
        fsp_id = current_user.candidate_profile.fsp_id

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        email_verified=current_user.email_verified,
        fsp_id=fsp_id,
        created_at=current_user.created_at,
    )
