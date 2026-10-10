"""Finite State Machine (FSM) for Candidate Invitations.

State Transition Graph:
                     ┌──────────────┐
                     │     SENT     │
                     └───────┬──────┘
                             │ view()
                             ▼
                     ┌──────────────┐
       ┌────────────►│    VIEWED    │────────────┐
       │             └───────┬──────┘            │
       │ accept()            │ decline()         │ withdraw() / expire()
       ▼                     ▼                   ▼
┌──────────────┐      ┌──────────────┐     ┌──────────────┐
│   ACCEPTED   │      │   DECLINED   │     │  WITHDRAWN / │
│ (Discloses   │      │(Reason req:  │     │   EXPIRED    │
│  contacts)   │      │SALARY, TECH, │     │              │
└──────┬───────┘      │FORMAT, NOT_L)│     └──────────────┘
       │ revoke()     └──────────────┘
       ▼
┌──────────────────┐
│ CONTACTS_REVOKED │  (the candidate hid their contacts again)
└──────────────────┘

APPLIED is the candidate's own application to a vacancy: contacts are disclosed from the start (ТЗ 2.2).
"""

from datetime import datetime, timezone

from backend.app.models.invitation import (
    DeclineReason,
    Invitation,
    InvitationStatus,
)


class InvitationFSMError(Exception):
    """Base exception for FSM errors."""


class InvalidStateTransitionError(InvitationFSMError):
    """Raised when attempting an unauthorized or invalid state transition."""
    def __init__(self, current_status: str, target_status: str, reason: str = ""):
        msg = f"Недопустимый переход из статуса '{current_status}' в '{target_status}'."
        if reason:
            msg += f" Причина: {reason}"
        super().__init__(msg)
        self.current_status = current_status
        self.target_status = target_status


class DeclineReasonRequiredError(InvitationFSMError):
    """Raised when declining an invitation without a required reason."""
    def __init__(self):
        super().__init__(
            "Для отклонения приглашения обязательно указать причину: "
            "SALARY, TECH_STACK, FORMAT или NOT_LOOKING."
        )


class InvitationExpiredError(InvitationFSMError):
    """Raised when trying to interact with an expired invitation."""
    def __init__(self):
        super().__init__("Срок действия приглашения истёк (14 дней). Операция невозможна.")


VALID_TRANSITIONS: dict[str, set[str]] = {
    InvitationStatus.SENT.value: {
        InvitationStatus.VIEWED.value,
        InvitationStatus.ACCEPTED.value,
        InvitationStatus.DECLINED.value,
        InvitationStatus.WITHDRAWN.value,
        InvitationStatus.EXPIRED.value,
    },
    InvitationStatus.APPLIED.value: {
        InvitationStatus.VIEWED.value,
        InvitationStatus.ACCEPTED.value,
        InvitationStatus.DECLINED.value,
        InvitationStatus.WITHDRAWN.value,
        InvitationStatus.EXPIRED.value,
    },
    InvitationStatus.VIEWED.value: {
        InvitationStatus.ACCEPTED.value,
        InvitationStatus.DECLINED.value,
        InvitationStatus.WITHDRAWN.value,
        InvitationStatus.EXPIRED.value,
    },
    InvitationStatus.ACCEPTED.value: {InvitationStatus.CONTACTS_REVOKED.value},
    # Terminal states
    InvitationStatus.CONTACTS_REVOKED.value: set(),
    InvitationStatus.DECLINED.value: set(),
    InvitationStatus.WITHDRAWN.value: set(),
    InvitationStatus.EXPIRED.value: set(),
}

VALID_DECLINE_REASONS: set[str] = {
    DeclineReason.SALARY.value,
    DeclineReason.TECH_STACK.value,
    DeclineReason.FORMAT.value,
    DeclineReason.NOT_LOOKING.value,
    DeclineReason.OTHER.value,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvitationFSM:
    """Encapsulates state transitions, validations, and side-effects."""

    @staticmethod
    def is_expired(invitation: Invitation, now: datetime | None = None) -> bool:
        """Checks if invitation has passed its 14-day validity window."""
        if invitation.status == InvitationStatus.EXPIRED.value:
            return True
        if invitation.status in (
            InvitationStatus.ACCEPTED.value,
            InvitationStatus.DECLINED.value,
            InvitationStatus.WITHDRAWN.value,
            InvitationStatus.CONTACTS_REVOKED.value,
        ):
            return False

        if now is None:
            now = utcnow()
        exp = invitation.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= exp

    @classmethod
    def apply_auto_expiry(cls, invitation: Invitation, now: datetime | None = None) -> bool:
        """Transitions invitation to EXPIRED if past validity date."""
        if cls.is_expired(invitation, now) and invitation.status in (InvitationStatus.SENT.value, InvitationStatus.VIEWED.value):
            invitation.status = InvitationStatus.EXPIRED.value
            invitation.resolved_at = now or utcnow()
            return True
        return False

    @classmethod
    def can_transition(cls, current_status: str, target_status: str) -> bool:
        return target_status in VALID_TRANSITIONS.get(current_status, set())

    @classmethod
    def transition_to_viewed(cls, invitation: Invitation) -> None:
        """Transitions SENT -> VIEWED when candidate opens invitation."""
        cls.apply_auto_expiry(invitation)
        if invitation.status == InvitationStatus.EXPIRED.value:
            raise InvitationExpiredError()

        if invitation.status == InvitationStatus.VIEWED.value:
            return  # Idempotent

        if not cls.can_transition(invitation.status, InvitationStatus.VIEWED.value):
            raise InvalidStateTransitionError(
                invitation.status,
                InvitationStatus.VIEWED.value,
                "Приглашение уже принято, отклонено или отозвано.",
            )

        invitation.status = InvitationStatus.VIEWED.value
        if not invitation.viewed_at:
            invitation.viewed_at = utcnow()

    @classmethod
    def transition_to_accepted(cls, invitation: Invitation) -> None:
        """Transitions VIEWED / SENT -> ACCEPTED (Triggers contact disclosure!)."""
        cls.apply_auto_expiry(invitation)
        if invitation.status == InvitationStatus.EXPIRED.value:
            raise InvitationExpiredError()

        if not cls.can_transition(invitation.status, InvitationStatus.ACCEPTED.value):
            raise InvalidStateTransitionError(
                invitation.status,
                InvitationStatus.ACCEPTED.value,
                "Невозможно принять приглашение из текущего состояния.",
            )

        now = utcnow()
        if not invitation.viewed_at:
            invitation.viewed_at = now
        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.resolved_at = now

    @classmethod
    def transition_to_declined(cls, invitation: Invitation, decline_reason: str) -> None:
        """Transitions VIEWED / SENT -> DECLINED (Requires valid decline reason)."""
        cls.apply_auto_expiry(invitation)
        if invitation.status == InvitationStatus.EXPIRED.value:
            raise InvitationExpiredError()

        if not cls.can_transition(invitation.status, InvitationStatus.DECLINED.value):
            raise InvalidStateTransitionError(
                invitation.status,
                InvitationStatus.DECLINED.value,
                "Невозможно отклонить уже завершённое приглашение.",
            )

        clean_reason = (decline_reason or "").strip().upper()
        if clean_reason not in VALID_DECLINE_REASONS:
            raise DeclineReasonRequiredError()

        now = utcnow()
        if not invitation.viewed_at:
            invitation.viewed_at = now
        invitation.status = InvitationStatus.DECLINED.value
        invitation.decline_reason = clean_reason
        invitation.resolved_at = now

    @classmethod
    def transition_to_withdrawn(cls, invitation: Invitation) -> None:
        """Transitions VIEWED / SENT -> WITHDRAWN (Employer action)."""
        cls.apply_auto_expiry(invitation)
        if invitation.status == InvitationStatus.EXPIRED.value:
            raise InvitationExpiredError()

        if not cls.can_transition(invitation.status, InvitationStatus.WITHDRAWN.value):
            raise InvalidStateTransitionError(
                invitation.status,
                InvitationStatus.WITHDRAWN.value,
                "Работодатель может отозвать только отправленные или просмотренные приглашения.",
            )

        invitation.status = InvitationStatus.WITHDRAWN.value
        invitation.resolved_at = utcnow()

    @classmethod
    def transition_to_contacts_revoked(cls, invitation: Invitation) -> None:
        """Transitions ACCEPTED -> CONTACTS_REVOKED (Candidate hides the contacts disclosed to the company)."""
        if not cls.can_transition(invitation.status, InvitationStatus.CONTACTS_REVOKED.value):
            raise InvalidStateTransitionError(
                invitation.status,
                InvitationStatus.CONTACTS_REVOKED.value,
                "Скрыть контакты можно только по принятому приглашению.",
            )
        invitation.status = InvitationStatus.CONTACTS_REVOKED.value
