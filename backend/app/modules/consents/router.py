
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

try:
    from backend.app.core.database import get_db
    from backend.app.models.user import User
    from backend.app.modules.auth.service import get_current_user
    from backend.app.modules.consents import service
    from backend.app.modules.consents.schemas import (
        ConsentGiveRequest,
        ConsentItemResponse,
        ConsentRevokeRequest,
        ConsentStatusResponse,
    )
except ImportError:
    from app.core.database import get_db
    from app.models.user import User
    from app.modules.auth.service import get_current_user
    from app.modules.consents import service
    from app.modules.consents.schemas import (
        ConsentGiveRequest,
        ConsentItemResponse,
        ConsentRevokeRequest,
        ConsentStatusResponse,
    )

router = APIRouter(prefix="/consents", tags=["Consents (152-FZ)"])


@router.get("", response_model=list[ConsentItemResponse])
def get_my_consents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve full history of current user's consents and versions."""
    return service.get_user_consents(db, current_user.id)


@router.get("/status", response_model=ConsentStatusResponse)
def get_consent_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get active consent statuses (personal data & profile distribution)."""
    return service.get_user_consent_status(db, current_user.id)


@router.post("/give", response_model=ConsentItemResponse, status_code=status.HTTP_200_OK)
def give_or_update_consent(
    req: ConsentGiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Give or re-affirm consent to a specific version of privacy policy / terms."""
    return service.give_consent(
        db,
        user=current_user,
        consent_type=req.consent_type.value,
        version=req.version,
    )


@router.post("/revoke", response_model=ConsentItemResponse, status_code=status.HTTP_200_OK)
def revoke_consent(
    req: ConsentRevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke consent according to 152-FZ. If profile distribution is revoked, profile is hidden from search."""
    return service.revoke_consent(
        db,
        user=current_user,
        consent_type=req.consent_type.value,
    )
