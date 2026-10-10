"""Service layer for invitations and contact privacy disclosure enforcement."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.candidate import CandidateProfile
from backend.app.models.company import Company, Need
from backend.app.models.invitation import AuditLog, Invitation, InvitationStatus
from backend.app.modules.invitations.fsm import (
    InvitationFSM,
)
from backend.app.modules.invitations.schemas import (
    CandidateAnonymizedCard,
    CandidateDisclosedContacts,
    CompanyShortInfo,
    InvitationCreate,
    InvitationResponse,
)


# Contacts are disclosed after an accepted invitation or the candidate's own application (ТЗ 2.2)
DISCLOSING_STATUSES = frozenset({InvitationStatus.ACCEPTED.value, InvitationStatus.APPLIED.value})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvitationService:
    """Business logic for invitation management and 152-FZ contact anonymization."""

    @staticmethod
    def _create_audit_log(
        db: Session,
        action: str,
        entity_id: str,
        user_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        log = AuditLog(
            action=action,
            entity_type="invitation",
            entity_id=entity_id,
            user_id=user_id,
            details=details or {},
            created_at=utcnow(),
        )
        db.add(log)

    @classmethod
    def create_invitation(
        cls,
        db: Session,
        payload: InvitationCreate,
        company_id: str,
        actor_user_id: str | None = None,
    ) -> InvitationResponse:
        """Employer creates an invitation.

        Enforces mandatory salary transparency in RUB (salary_from <= salary_to and salary_from > 0).
        """
        candidate = db.query(CandidateProfile).filter(CandidateProfile.id == payload.candidate_profile_id).first()
        if not candidate:
            raise ValueError(f"Профиль кандидата с ID {payload.candidate_profile_id} не найден.")

        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise ValueError(f"Компания с ID {company_id} не найдена.")

        if payload.need_id:
            need = db.query(Need).filter(Need.id == payload.need_id).first()
            if not need:
                raise ValueError(f"Потребность {payload.need_id} не найдена.")
                
            existing_invitation = db.query(Invitation).filter(
                Invitation.candidate_profile_id == payload.candidate_profile_id,
                Invitation.need_id == payload.need_id
            ).first()
            if existing_invitation:
                raise ValueError("Приглашение этому кандидату на данную вакансию уже существует.")
        
        # Защита от повторных приглашений одному кандидату
        recent_invitation = db.query(Invitation).filter(
            Invitation.candidate_profile_id == payload.candidate_profile_id,
            Invitation.company_id == company_id,
            Invitation.status.in_([InvitationStatus.SENT.value, InvitationStatus.VIEWED.value, InvitationStatus.ACCEPTED.value])
        ).first()
        if recent_invitation:
            raise ValueError("Вы уже отправили активное приглашение этому кандидату.")

        sal_type = (payload.salary_type or "NET").upper()
        is_gr = bool(payload.is_gross or (sal_type == "GROSS"))

        invitation = Invitation(
            company_id=company_id,
            candidate_profile_id=payload.candidate_profile_id,
            need_id=payload.need_id,
            status=InvitationStatus.SENT.value,
            salary_from=payload.salary_from,
            salary_to=payload.salary_to,
            salary_type="GROSS" if is_gr else "NET",
            is_gross=is_gr,
            message=payload.message,
            contact_method=payload.contact_method.upper(),
            sent_at=utcnow(),
            expires_at=utcnow() + timedelta(days=14),
        )
        db.add(invitation)
        db.flush()

        cls._create_audit_log(
            db=db,
            action="INVITATION_SENT",
            entity_id=invitation.id,
            user_id=actor_user_id,
            details={
                "salary_from": payload.salary_from,
                "salary_to": payload.salary_to,
                "salary_type": invitation.salary_type,
                "is_gross": invitation.is_gross,
                "candidate_profile_id": payload.candidate_profile_id,
                "company_id": company_id,
            },
        )
        db.commit()
        db.refresh(invitation)

        return cls.format_response(invitation, is_employer_view=True)

    @classmethod
    def view_invitation(
        cls,
        db: Session,
        invitation_id: str,
        actor_user_id: str | None = None,
    ) -> InvitationResponse:
        """Candidate views the invitation. Transitions SENT -> VIEWED."""
        invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
        if not invitation:
            raise ValueError(f"Приглашение с ID {invitation_id} не найдено.")

        InvitationFSM.transition_to_viewed(invitation)

        cls._create_audit_log(
            db=db,
            action="INVITATION_VIEWED",
            entity_id=invitation.id,
            user_id=actor_user_id,
        )
        db.commit()
        db.refresh(invitation)
        return cls.format_response(invitation, is_employer_view=False)

    @classmethod
    def accept_invitation(
        cls,
        db: Session,
        invitation_id: str,
        actor_user_id: str | None = None,
    ) -> InvitationResponse:
        """Candidate accepts the invitation. Transitions VIEWED/SENT -> ACCEPTED.

        CRITICAL: Triggers contact disclosure! Contacts are revealed to the employer.
        """
        invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
        if not invitation:
            raise ValueError(f"Приглашение с ID {invitation_id} не найдено.")

        InvitationFSM.transition_to_accepted(invitation)

        cls._create_audit_log(
            db=db,
            action="INVITATION_ACCEPTED",
            entity_id=invitation.id,
            user_id=actor_user_id,
            details={
                "contacts_disclosed": True,
                "disclosed_at": invitation.resolved_at.isoformat() if invitation.resolved_at else None,
            },
        )
        db.commit()
        db.refresh(invitation)
        return cls.format_response(invitation, is_employer_view=False)

    @classmethod
    def decline_invitation(
        cls,
        db: Session,
        invitation_id: str,
        decline_reason: str,
        actor_user_id: str | None = None,
    ) -> InvitationResponse:
        """Candidate declines invitation. Transitions VIEWED/SENT -> DECLINED."""
        invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
        if not invitation:
            raise ValueError(f"Приглашение с ID {invitation_id} не найдено.")

        InvitationFSM.transition_to_declined(invitation, decline_reason=decline_reason)

        cls._create_audit_log(
            db=db,
            action="INVITATION_DECLINED",
            entity_id=invitation.id,
            user_id=actor_user_id,
            details={"decline_reason": invitation.decline_reason},
        )
        db.commit()
        db.refresh(invitation)
        return cls.format_response(invitation, is_employer_view=False)

    @classmethod
    def withdraw_invitation(
        cls,
        db: Session,
        invitation_id: str,
        company_id: str | None = None,
        actor_user_id: str | None = None,
    ) -> InvitationResponse:
        """Employer withdraws an invitation. Transitions SENT/VIEWED -> WITHDRAWN."""
        query = db.query(Invitation).filter(Invitation.id == invitation_id)
        if company_id:
            query = query.filter(Invitation.company_id == company_id)
        invitation = query.first()
        if not invitation:
            raise ValueError(f"Приглашение {invitation_id} не найдено или не принадлежит компании.")

        InvitationFSM.transition_to_withdrawn(invitation)

        cls._create_audit_log(
            db=db,
            action="INVITATION_WITHDRAWN",
            entity_id=invitation.id,
            user_id=actor_user_id,
        )
        db.commit()
        db.refresh(invitation)
        return cls.format_response(invitation, is_employer_view=True)

    @classmethod
    def revoke_contacts(
        cls,
        db: Session,
        invitation: Invitation,
        actor_user_id: str | None = None,
    ) -> InvitationResponse:
        """Candidate hides contacts disclosed by an accepted invitation. Transitions ACCEPTED -> CONTACTS_REVOKED."""
        InvitationFSM.transition_to_contacts_revoked(invitation)
        cls._create_audit_log(db=db, action="CONTACTS_REVOKED", entity_id=invitation.id, user_id=actor_user_id)
        db.commit()
        db.refresh(invitation)
        return cls.format_response(invitation, is_employer_view=False)

    @classmethod
    def get_candidate_invitations(
        cls,
        db: Session,
        candidate_profile_id: str,
        status_filter: str | None = None,
    ) -> list[InvitationResponse]:
        """Fetch all invitations for a candidate with auto-expiry check."""
        query = db.query(Invitation).filter(Invitation.candidate_profile_id == candidate_profile_id)
        if status_filter:
            query = query.filter(Invitation.status == status_filter.upper())
        invitations = query.order_by(Invitation.sent_at.desc()).all()

        modified = False
        for inv in invitations:
            if InvitationFSM.apply_auto_expiry(inv):
                modified = True
        if modified:
            db.commit()

        return [cls.format_response(inv, is_employer_view=False) for inv in invitations]

    @classmethod
    def get_company_invitations(
        cls,
        db: Session,
        company_id: str,
        status_filter: str | None = None,
        need_id: str | None = None,
    ) -> list[InvitationResponse]:
        """Fetch all invitations sent by an employer with auto-expiry check."""
        query = db.query(Invitation).filter(Invitation.company_id == company_id)
        if status_filter:
            query = query.filter(Invitation.status == status_filter.upper())
        if need_id:
            query = query.filter(Invitation.need_id == need_id)
        invitations = query.order_by(Invitation.sent_at.desc()).all()

        modified = False
        for inv in invitations:
            if InvitationFSM.apply_auto_expiry(inv):
                modified = True
        if modified:
            db.commit()

        return [cls.format_response(inv, is_employer_view=True) for inv in invitations]

    @classmethod
    def format_response(
        cls,
        invitation: Invitation,
        is_employer_view: bool = False,
    ) -> InvitationResponse:
        """Constructs response enforcing 152-FZ contact anonymization.

        Contacts (phone, telegram, email) are disclosed only when the candidate accepted the invitation or applied
        to the vacancy themselves (ТЗ 2.2). Otherwise only the candidate card without contacts is provided.
        """
        # Company Info
        company_info = None
        if invitation.company:
            company_info = CompanyShortInfo(
                id=invitation.company.id,
                name=invitation.company.name,
                inn=invitation.company.inn,
                website=invitation.company.website,
                logo_url=invitation.company.logo_url,
                is_verified=invitation.company.is_verified,
            )

        candidate = invitation.candidate_profile

        # Candidate Anonymized Card
        cand_card = None
        if candidate:
            sal_type_cand = getattr(candidate, "salary_type", "NET") or "NET"
            is_gr_cand = getattr(candidate, "is_gross", False) or (sal_type_cand == "GROSS")
            sal_disp_cand = None
            if candidate.desired_salary_min:
                label_c = " (до вычета НДФЛ / Гросс)" if is_gr_cand else " (на руки / Нетто)"
                sal_disp_cand = f"{candidate.desired_salary_min:,} ₽{label_c}".replace(",", " ")

            is_unconf = not candidate.confirmed_grade or candidate.confirmed_grade.strip().upper() in (
                "UNCONFIRMED", "НЕ_ПОДТВЕРЖДЕН", "НЕ ПОДТВЕРЖДЕН", "НЕ ПОДТВЕРЖДЁН", "NONE"
            )

            # the name is visible to employers as in the matching card (Q&A VS.4); contacts are not
            full_name_cand = f"{candidate.first_name or ''} {candidate.last_name or ''}".strip() or f"Кандидат #{candidate.id[:8]}"

            cand_card = CandidateAnonymizedCard(
                id=candidate.id,
                full_name=full_name_cand,
                confirmed_category=candidate.confirmed_category,
                confirmed_specialization=candidate.confirmed_specialization,
                confirmed_grade=candidate.confirmed_grade or "Не подтверждён",
                is_grade_confirmed=not is_unconf,
                grade_status="UNCONFIRMED" if is_unconf else "CONFIRMED",
                category_percentile=candidate.category_percentile,
                fsp_score=candidate.fsp_score or 0.0,
                is_fsp_verified=candidate.is_fsp_verified or False,
                desired_salary_min=candidate.desired_salary_min,
                salary_type=sal_type_cand,
                is_gross=is_gr_cand,
                salary_display=sal_disp_cand,
                work_format=candidate.work_format,
                city=candidate.city,
                contacts_hidden=invitation.status not in DISCLOSING_STATUSES,
            )

        # Contact disclosure logic
        disclosed_contacts = None
        contacts_disclosed = False

        if candidate and invitation.status in DISCLOSING_STATUSES:
            contacts_disclosed = True
            cand_email = None
            if candidate.user:
                cand_email = candidate.user.email

            disclosed_contacts = CandidateDisclosedContacts(
                first_name=candidate.first_name,
                last_name=candidate.last_name,
                phone=candidate.phone,
                telegram=candidate.telegram,
                email=cand_email,
                disclosed_at=invitation.resolved_at,
            )

        inv_sal_type = getattr(invitation, "salary_type", "NET") or "NET"
        inv_is_gross = getattr(invitation, "is_gross", False) or (inv_sal_type == "GROSS")
        label_inv = " (до вычета НДФЛ / Гросс)" if inv_is_gross else " (на руки / Нетто)"
        inv_sal_disp = f"{invitation.salary_from:,} – {invitation.salary_to:,} ₽{label_inv}".replace(",", " ")

        return InvitationResponse(
            id=invitation.id,
            company_id=invitation.company_id,
            candidate_profile_id=invitation.candidate_profile_id,
            need_id=invitation.need_id,
            status=invitation.status,
            salary_from=invitation.salary_from,
            salary_to=invitation.salary_to,
            salary_currency="RUB",
            salary_type=inv_sal_type,
            is_gross=inv_is_gross,
            salary_display=inv_sal_disp,
            message=invitation.message,
            contact_method=invitation.contact_method,
            decline_reason=invitation.decline_reason,
            sent_at=invitation.sent_at,
            viewed_at=invitation.viewed_at,
            resolved_at=invitation.resolved_at,
            expires_at=invitation.expires_at,
            is_expired=(invitation.status == InvitationStatus.EXPIRED.value),
            company=company_info,
            candidate_card=cand_card,
            candidate_contacts=disclosed_contacts,
            contacts_disclosed=contacts_disclosed,
        )
