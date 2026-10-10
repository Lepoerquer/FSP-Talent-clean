from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

try:
    from backend.app.models.invitation import AuditLog
    from backend.app.models.user import Consent, User
    from backend.app.modules.consents.schemas import (
        ConsentItemResponse,
        ConsentStatusResponse,
    )
except ImportError:
    from app.models.invitation import AuditLog
    from app.models.user import Consent, User
    from app.modules.consents.schemas import ConsentItemResponse, ConsentStatusResponse

CONSENT_TITLES = {
    "PERSONAL_DATA": {
        "title": "Согласие на обработку персональных данных (152-ФЗ)",
        "description": "Разрешает хранение и обработку учетных данных, email и результатов тестирования в рамках сервиса FSP-Talent."
    },
    "PROFILE_DISTRIBUTION": {
        "title": "Согласие на распространение профиля работодателям (152-ФЗ ст. 10.1)",
        "description": "Разрешает отображение анонимизированной квалификационной карточки кандидата в выдаче подбора и передачу контактов при взаимном принятии приглашения."
    }
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enrich_consent(c: Consent) -> ConsentItemResponse:
    meta = CONSENT_TITLES.get(c.consent_type, {"title": c.consent_type, "description": ""})
    return ConsentItemResponse(
        id=c.id,
        user_id=c.user_id,
        consent_type=c.consent_type,
        version=c.version,
        is_given=c.is_given,
        given_at=c.given_at,
        revoked_at=c.revoked_at,
        title=meta["title"],
        description=meta["description"],
    )


def get_user_consents(db: Session, user_id: str) -> list[ConsentItemResponse]:
    consents = db.query(Consent).filter(Consent.user_id == user_id).all()
    return [enrich_consent(c) for c in consents]


def get_user_consent_status(db: Session, user_id: str) -> ConsentStatusResponse:
    consents = db.query(Consent).filter(Consent.user_id == user_id).all()
    
    pd_active = False
    dist_active = False
    for c in consents:
        if c.consent_type == "PERSONAL_DATA" and c.is_given:
            pd_active = True
        elif c.consent_type == "PROFILE_DISTRIBUTION" and c.is_given:
            dist_active = True

    return ConsentStatusResponse(
        user_id=user_id,
        personal_data_active=pd_active,
        profile_distribution_active=dist_active,
        consents=[enrich_consent(c) for c in consents],
    )


def give_consent(db: Session, user: User, consent_type: str, version: str = "1.0") -> ConsentItemResponse:
    now = utcnow()
    consent = (
        db.query(Consent)
        .filter(Consent.user_id == user.id, Consent.consent_type == consent_type)
        .first()
    )

    if consent:
        consent.is_given = True
        consent.version = version
        consent.given_at = now
        consent.revoked_at = None
    else:
        consent = Consent(
            user_id=user.id,
            consent_type=consent_type,
            version=version,
            is_given=True,
            given_at=now,
        )
        db.add(consent)

    # If re-enabling profile distribution and user has candidate profile, un-hide profile
    if consent_type == "PROFILE_DISTRIBUTION" and user.candidate_profile:
        if user.candidate_profile.status == "HIDDEN":
            user.candidate_profile.status = "ACTIVELY_SEARCHING"

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="CONSENT_GIVEN",
        entity_type="consent",
        entity_id=consent.id if consent.id else None,
        details={"consent_type": consent_type, "version": version},
    )
    db.add(audit)
    db.commit()
    db.refresh(consent)
    return enrich_consent(consent)


def revoke_consent(db: Session, user: User, consent_type: str) -> ConsentItemResponse:
    consent = (
        db.query(Consent)
        .filter(Consent.user_id == user.id, Consent.consent_type == consent_type)
        .first()
    )

    if not consent or not consent.is_given:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Согласие типа '{consent_type}' уже отозвано или не было предоставлено.",
        )

    now = utcnow()
    consent.is_given = False
    consent.revoked_at = now

    # If revoking profile distribution, automatically hide profile from search
    if consent_type == "PROFILE_DISTRIBUTION" and user.candidate_profile:
        user.candidate_profile.status = "HIDDEN"

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="CONSENT_REVOKED",
        entity_type="consent",
        entity_id=consent.id,
        details={"consent_type": consent_type, "revoked_at": now.isoformat()},
    )
    db.add(audit)
    db.commit()
    db.refresh(consent)
    return enrich_consent(consent)
