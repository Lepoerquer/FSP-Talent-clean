"""FastAPI Router for Invitations and Contact Anonymization Lifecycle.

Access rules (ТЗ 2.1, 2.2): an employer sends and sees only their own company's invitations; a candidate sees and
answers only invitations addressed to them. Contacts are disclosed after the candidate accepts an invitation or
applies to a vacancy themselves.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.models.candidate import CandidateProfile
from backend.app.models.company import Company
from backend.app.models.invitation import Invitation, InvitationStatus
from backend.app.models.user import User
from backend.app.modules.auth.service import get_current_candidate, get_current_company, get_current_user
from backend.app.modules.invitations.fsm import (
    DeclineReasonRequiredError,
    InvalidStateTransitionError,
    InvitationExpiredError,
)
from backend.app.modules.invitations.schemas import (
    InvitationCreate,
    InvitationResponse,
    InvitationStatusTransitionRequest,
)
from backend.app.modules.invitations.service import InvitationService

router = APIRouter(prefix="/invitations", tags=["Invitations & Privacy"])

NOT_FOUND = {"error_code": "INVITATION_NOT_FOUND", "message": "Приглашение не найдено."}


def _own_invitation(db: Session, invitation_id: str, candidate: CandidateProfile) -> Invitation:
    """An invitation addressed to the signed-in candidate; anyone else's is reported as missing."""
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if not invitation or invitation.candidate_profile_id != candidate.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    if invitation.status == InvitationStatus.APPLIED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "OWN_APPLICATION",
                "message": "Это ваш отклик на вакансию: решение по нему принимает работодатель.",
            },
        )
    return invitation


@router.post(
    "",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Отправить приглашение кандидату с обязательной вилкой зарплаты в RUB",
)
def create_invitation(
    payload: InvitationCreate,
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Работодатель отправляет персонализированное приглашение кандидату от имени своей компании.

    Ключевые правила (152-ФЗ и регламент платформы):
    - Обязательно указание зарплаты 'от' и 'до' в рублях (salary_from > 0, salary_from <= salary_to).
    - Контакты кандидата остаются скрытыми (anonymized) до явного принятия приглашения.
    """
    if payload.company_id and payload.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN", "message": "Приглашение можно отправить только от своей компании."},
        )
    try:
        return InvitationService.create_invitation(
            db=db,
            payload=payload,
            company_id=company.id,
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_INVITATION_DATA", "message": str(exc)},
        )


@router.get(
    "/candidate",
    response_model=list[InvitationResponse],
    summary="Приглашения и отклики текущего кандидата",
)
def get_candidate_invitations(
    status_filter: str | None = Query(None, description="Фильтр по статусу (SENT, VIEWED, ACCEPTED, DECLINED, APPLIED)"),
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Входящие приглашения и собственные отклики кандидата с проверкой автоматического истечения срока (14 дней)."""
    return InvitationService.get_candidate_invitations(
        db=db,
        candidate_profile_id=candidate.id,
        status_filter=status_filter,
    )


@router.get(
    "/company",
    response_model=list[InvitationResponse],
    summary="Приглашения и входящие отклики компании текущего работодателя",
)
def get_company_invitations(
    status_filter: str | None = Query(None, description="Фильтр по статусу"),
    need_id: str | None = Query(None, description="Фильтр по потребности"),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Возвращает отправленные компанией приглашения и отклики кандидатов на её вакансии.

    Контакты кандидатов раскрываются только для принятых приглашений и для откликов кандидата.
    Для остальных статусов возвращается анонимизированная карточка.
    """
    return InvitationService.get_company_invitations(
        db=db,
        company_id=company.id,
        status_filter=status_filter,
        need_id=need_id,
    )


@router.post(
    "/{id}/view",
    response_model=InvitationResponse,
    summary="Отметить приглашение как просмотренное кандидатом",
)
def mark_invitation_viewed(
    id: str = Path(..., description="ID приглашения"),
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Переход автомата: SENT -> VIEWED."""
    _own_invitation(db, id, candidate)
    try:
        return InvitationService.view_invitation(db=db, invitation_id=id, actor_user_id=candidate.user_id)
    except (InvalidStateTransitionError, InvitationExpiredError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_STATE_TRANSITION", "message": str(exc)},
        )


@router.post(
    "/{id}/accept",
    response_model=InvitationResponse,
    summary="Принять приглашение работодателя (РАСКРЫВАЕТ КОНТАКТЫ)",
)
def accept_invitation(
    id: str = Path(..., description="ID приглашения"),
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Переход автомата: VIEWED -> ACCEPTED.

    ЮРИДИЧЕСКИЙ ЭФФЕКТ (152-ФЗ):
    Кандидат выражает согласие на раскрытие прямых контактных данных
    (телефон, telegram, email, ФИО) пригласившей компании.
    """
    _own_invitation(db, id, candidate)
    try:
        return InvitationService.accept_invitation(db=db, invitation_id=id, actor_user_id=candidate.user_id)
    except (InvalidStateTransitionError, InvitationExpiredError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_STATE_TRANSITION", "message": str(exc)},
        )


@router.post(
    "/{id}/decline",
    response_model=InvitationResponse,
    summary="Отклонить приглашение с обязательным указанием причины",
)
def decline_invitation(
    id: str = Path(..., description="ID приглашения"),
    req: InvitationStatusTransitionRequest = ...,
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Переход автомата: SENT/VIEWED -> DECLINED.

    Обязательна причина отказа: SALARY, TECH_STACK, FORMAT, NOT_LOOKING, OTHER.
    """
    if not req.decline_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "DECLINE_REASON_REQUIRED",
                "message": "Для отклонения приглашения обязательно указать причину (SALARY, TECH_STACK, FORMAT, NOT_LOOKING).",
            },
        )
    _own_invitation(db, id, candidate)
    try:
        return InvitationService.decline_invitation(
            db=db,
            invitation_id=id,
            decline_reason=req.decline_reason.value,
            actor_user_id=candidate.user_id,
        )
    except (InvalidStateTransitionError, DeclineReasonRequiredError, InvitationExpiredError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_STATE_TRANSITION", "message": str(exc)},
        )


@router.post(
    "/{id}/withdraw",
    response_model=InvitationResponse,
    summary="Отозвать приглашение (действие работодателя)",
)
def withdraw_invitation(
    id: str = Path(..., description="ID приглашения"),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Переход автомата: SENT/VIEWED -> WITHDRAWN. Только для приглашений своей компании."""
    try:
        return InvitationService.withdraw_invitation(
            db=db,
            invitation_id=id,
            company_id=company.id,
            actor_user_id=current_user.id,
        )
    except (InvalidStateTransitionError, InvitationExpiredError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_STATE_TRANSITION", "message": str(exc)},
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)


@router.post(
    "/{invitation_id}/revoke-contacts",
    response_model=InvitationResponse,
    summary="Отзыв доступа к контактам (Дополнительный плюс, Q&A)",
    description="Кандидат скрывает свои контакты (email, телефон, телеграм) от компании после принятия приглашения.",
)
def revoke_contact_access(
    invitation_id: str,
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    invitation = _own_invitation(db, invitation_id, candidate)
    try:
        return InvitationService.revoke_contacts(db=db, invitation=invitation, actor_user_id=candidate.user_id)
    except InvalidStateTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_STATE_TRANSITION", "message": str(exc)},
        )
