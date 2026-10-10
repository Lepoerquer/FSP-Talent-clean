import enum
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

try:
    from backend.app.core.database import Base
except ImportError:
    from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=14)


class InvitationStatus(str, enum.Enum):
    SENT = "SENT"
    APPLIED = "APPLIED"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    CONTACTS_REVOKED = "CONTACTS_REVOKED"  # accepted, then the candidate hid their contacts again


class DeclineReason(str, enum.Enum):
    SALARY = "SALARY"
    TECH_STACK = "TECH_STACK"
    FORMAT = "FORMAT"
    NOT_LOOKING = "NOT_LOOKING"
    OTHER = "OTHER"


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    need_id = Column(String(36), ForeignKey("needs.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # State machine status
    status = Column(String(50), default=InvitationStatus.SENT.value, nullable=False, index=True)
    
    # Mandatory salary transparency in RUB (FZ & TZ requirement)
    salary_from = Column(Integer, nullable=False)
    salary_to = Column(Integer, nullable=False)
    salary_type = Column(String(20), default="NET", nullable=False)  # NET (на руки), GROSS (до вычета НДФЛ)
    is_gross = Column(Boolean, default=False, nullable=False)
    
    message = Column(Text, nullable=False)
    contact_method = Column(String(100), default="TELEGRAM", nullable=False)
    decline_reason = Column(String(100), nullable=True)
    
    sent_at = Column(DateTime, default=utcnow, nullable=False)
    viewed_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, default=default_expiry, nullable=False)

    # Relationships
    company = relationship("Company", back_populates="invitations")
    candidate_profile = relationship("CandidateProfile", back_populates="invitations")
    need = relationship("Need", back_populates="invitations")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # INVITATION_SENT, CONTACTS_REVEALED, etc.
    entity_type = Column(String(100), nullable=False)        # invitation, candidate_profile, consent
    entity_id = Column(String(36), nullable=True, index=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User")
