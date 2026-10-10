"""Unit tests for Invitations Finite State Machine (FSM), Salary Range Validation, and Contact Privacy (152-FZ)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.candidate import CandidateProfile
from backend.app.models.company import Company
from backend.app.models.invitation import (
    AuditLog,
    DeclineReason,
    Invitation,
    InvitationStatus,
)
from backend.app.models.user import User
from backend.app.modules.invitations.fsm import (
    DeclineReasonRequiredError,
    InvalidStateTransitionError,
    InvitationExpiredError,
)
from backend.app.modules.invitations.schemas import (
    InvitationCreate,
)
from backend.app.modules.invitations.service import InvitationService


@pytest.fixture
def db_session():
    """In-memory SQLite database session for isolated testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_data(db_session):
    """Seeds test company, candidate user and candidate profile."""
    company = Company(
        id="comp-1",
        name="ООО «Яндекс Технологии»",
        inn="7704340310",
        is_verified=True,
    )
    db_session.add(company)

    user = User(
        id="user-cand-1",
        email="alex.ivanov@example.com",
        role="CANDIDATE",
    )
    db_session.add(user)

    candidate = CandidateProfile(
        id="cand-1",
        user_id="user-cand-1",
        first_name="Алексей",
        last_name="Иванов",
        phone="+7 (999) 123-45-67",
        telegram="@alex_ivanov_dev",
        status="ACTIVELY_SEARCHING",
        confirmed_category="Backend · Middle",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        category_percentile=85,
        fsp_score=0.72,
        is_fsp_verified=True,
        desired_salary_min=200000,
        work_format="REMOTE",
        city="Москва",
        hide_contacts_globally=True,
    )
    db_session.add(candidate)
    db_session.commit()

    return {"company": company, "candidate": candidate, "user": user}


# ==============================================================================
# 1. SALARY RANGE VALIDATION TESTS (TZ & FZ MANDATORY REQUIREMENT)
# ==============================================================================

def test_salary_validation_valid():
    """Valid salary range in RUB."""
    create_dto = InvitationCreate(
        candidate_profile_id="cand-1",
        company_id="comp-1",
        salary_from=220000,
        salary_to=280000,
        message="Приглашаем на позицию Middle Backend Developer в команду инфраструктуры",
        contact_method="TELEGRAM",
    )
    assert create_dto.salary_from == 220000
    assert create_dto.salary_to == 280000
    assert create_dto.salary_from <= create_dto.salary_to


def test_salary_validation_inverted_fails():
    """salary_from > salary_to must raise ValidationError."""
    with pytest.raises(ValueError, match="не может превышать"):
        InvitationCreate(
            candidate_profile_id="cand-1",
            salary_from=300000,
            salary_to=250000,  # Invalid: from > to
            message="Приглашаем в команду",
        )


def test_salary_validation_negative_or_zero_fails():
    """salary_from <= 0 must fail validation."""
    with pytest.raises(ValueError, match="строго положительной"):
        InvitationCreate(
            candidate_profile_id="cand-1",
            salary_from=0,
            salary_to=200000,
            message="Приглашаем в команду",
        )

    with pytest.raises(ValueError, match="строго положительной"):
        InvitationCreate(
            candidate_profile_id="cand-1",
            salary_from=-50000,
            salary_to=150000,
            message="Приглашаем в команду",
        )


# ==============================================================================
# 2. FSM TRANSITIONS AND PRIVACY DISCLOSURE TESTS
# ==============================================================================

def test_invitation_sent_to_viewed_to_accepted_discloses_contacts(db_session, seed_data):
    """Happy path: SENT -> VIEWED -> ACCEPTED.

    Verify contacts are HIDDEN initially and REVEALED upon ACCEPTED.
    """
    create_dto = InvitationCreate(
        candidate_profile_id="cand-1",
        salary_from=220000,
        salary_to=280000,
        message="Здравствуйте! Мы впечатлены вашими результатами в тестировании.",
        contact_method="TELEGRAM",
    )
    # 1. Employer creates invitation -> status SENT
    inv_resp = InvitationService.create_invitation(
        db=db_session,
        payload=create_dto,
        company_id="comp-1",
        actor_user_id="employer-user-1",
    )
    assert inv_resp.status == "SENT"
    assert inv_resp.contacts_disclosed is False
    assert inv_resp.candidate_contacts is None  # Contacts hidden!

    # Verify audit log recorded
    log_sent = db_session.query(AuditLog).filter(AuditLog.action == "INVITATION_SENT").first()
    assert log_sent is not None
    assert log_sent.entity_id == inv_resp.id

    # 2. Candidate views invitation -> status VIEWED
    view_resp = InvitationService.view_invitation(
        db=db_session,
        invitation_id=inv_resp.id,
        actor_user_id="user-cand-1",
    )
    assert view_resp.status == "VIEWED"
    assert view_resp.viewed_at is not None
    assert view_resp.contacts_disclosed is False
    assert view_resp.candidate_contacts is None  # Still hidden!

    # 3. Candidate accepts invitation -> status ACCEPTED (CONTACT DISCLOSURE TRIGGERED!)
    accept_resp = InvitationService.accept_invitation(
        db=db_session,
        invitation_id=inv_resp.id,
        actor_user_id="user-cand-1",
    )
    assert accept_resp.status == "ACCEPTED"
    assert accept_resp.contacts_disclosed is True
    assert accept_resp.candidate_contacts is not None
    assert accept_resp.candidate_contacts.first_name == "Алексей"
    assert accept_resp.candidate_contacts.last_name == "Иванов"
    assert accept_resp.candidate_contacts.phone == "+7 (999) 123-45-67"
    assert accept_resp.candidate_contacts.telegram == "@alex_ivanov_dev"
    assert accept_resp.candidate_contacts.email == "alex.ivanov@example.com"

    # Audit log verification
    log_accepted = db_session.query(AuditLog).filter(AuditLog.action == "INVITATION_ACCEPTED").first()
    assert log_accepted is not None
    assert log_accepted.details.get("contacts_disclosed") is True


def test_invitation_decline_with_mandatory_reasons(db_session, seed_data):
    """Declining requires a valid decline reason: SALARY, TECH_STACK, FORMAT, NOT_LOOKING."""
    create_dto = InvitationCreate(
        candidate_profile_id="cand-1",
        salary_from=150000,
        salary_to=180000,
        message="Приглашаем на собеседование.",
    )
    inv = InvitationService.create_invitation(db=db_session, payload=create_dto, company_id="comp-1")

    # Reject without valid reason raises DeclineReasonRequiredError
    with pytest.raises(DeclineReasonRequiredError):
        InvitationService.decline_invitation(
            db=db_session,
            invitation_id=inv.id,
            decline_reason="",
        )

    # Reject with valid reason SALARY succeeds
    declined_resp = InvitationService.decline_invitation(
        db=db_session,
        invitation_id=inv.id,
        decline_reason=DeclineReason.SALARY.value,
    )
    assert declined_resp.status == "DECLINED"
    assert declined_resp.decline_reason == "SALARY"
    assert declined_resp.contacts_disclosed is False
    assert declined_resp.candidate_contacts is None


def test_invitation_withdrawal_by_employer(db_session, seed_data):
    """Employer withdraws an invitation."""
    create_dto = InvitationCreate(
        candidate_profile_id="cand-1",
        salary_from=200000,
        salary_to=250000,
        message="Приглашение для проверки отзыва.",
    )
    inv = InvitationService.create_invitation(db=db_session, payload=create_dto, company_id="comp-1")

    withdrawn = InvitationService.withdraw_invitation(
        db=db_session,
        invitation_id=inv.id,
        company_id="comp-1",
    )
    assert withdrawn.status == "WITHDRAWN"


def test_terminal_states_cannot_transition(db_session, seed_data):
    """Once ACCEPTED or DECLINED, no further state transitions are allowed."""
    create_dto = InvitationCreate(
        candidate_profile_id="cand-1",
        salary_from=200000,
        salary_to=250000,
        message="Приглашение для проверки терминальных состояний.",
    )
    inv = InvitationService.create_invitation(db=db_session, payload=create_dto, company_id="comp-1")
    InvitationService.accept_invitation(db=db_session, invitation_id=inv.id)

    # Cannot decline after accepting
    with pytest.raises(InvalidStateTransitionError):
        InvitationService.decline_invitation(
            db=db_session,
            invitation_id=inv.id,
            decline_reason="FORMAT",
        )

    # Cannot withdraw after accepting
    with pytest.raises(InvalidStateTransitionError):
        InvitationService.withdraw_invitation(
            db=db_session,
            invitation_id=inv.id,
            company_id="comp-1",
        )


def test_auto_expiry_after_14_days(db_session, seed_data):
    """Invitations past 14 days are automatically marked EXPIRED."""
    inv = Invitation(
        company_id="comp-1",
        candidate_profile_id="cand-1",
        status=InvitationStatus.SENT.value,
        salary_from=200000,
        salary_to=250000,
        message="Старое приглашение",
        sent_at=datetime.now(timezone.utc) - timedelta(days=15),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired yesterday
    )
    db_session.add(inv)
    db_session.commit()

    # Querying candidate invitations triggers auto-expiry
    c_invs = InvitationService.get_candidate_invitations(db=db_session, candidate_profile_id="cand-1")
    expired_inv = next(i for i in c_invs if i.id == inv.id)
    assert expired_inv.status == "EXPIRED"
    assert expired_inv.is_expired is True

    # Trying to accept an expired invitation raises InvitationExpiredError
    with pytest.raises(InvitationExpiredError):
        InvitationService.accept_invitation(db=db_session, invitation_id=inv.id)
