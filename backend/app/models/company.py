import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

try:
    from backend.app.core.database import Base
except ImportError:
    from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    inn = Column(String(20), nullable=True, index=True)
    website = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    logo_url = Column(String(255), nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    direction = Column(String(255), nullable=True)
    contacts = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    members = relationship("EmployerMember", back_populates="company", cascade="all, delete-orphan")
    needs = relationship("Need", back_populates="company", cascade="all, delete-orphan")
    vacancies = relationship("Vacancy", back_populates="company", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="company", cascade="all, delete-orphan")
    challenges = relationship("EmployerChallenge", back_populates="company", cascade="all, delete-orphan")


class EmployerMember(Base):
    __tablename__ = "employer_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), default="RECRUITER", nullable=False)  # OWNER, ADMIN, RECRUITER
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="employer_memberships")
    company = relationship("Company", back_populates="members")


class Need(Base):
    __tablename__ = "needs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    raw_description = Column(Text, nullable=True)
    target_specialization = Column(String(100), nullable=False)
    target_grade = Column(String(50), nullable=False)
    required_skills = Column(JSON, nullable=True)  # List of skill names / codes
    salary_budget_min = Column(Integer, nullable=True)  # in RUB
    salary_budget_max = Column(Integer, nullable=True)  # in RUB
    salary_type = Column(String(20), default="NET", nullable=False)  # NET (на руки), GROSS (до вычета)
    is_gross = Column(Boolean, default=False, nullable=False)
    work_format = Column(String(50), default="REMOTE", nullable=True)  # REMOTE, HYBRID, OFFICE
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    company = relationship("Company", back_populates="needs")
    selection_snapshots = relationship("SelectionSnapshot", back_populates="need", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="need")


class SelectionSnapshot(Base):
    __tablename__ = "selection_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    need_id = Column(String(36), ForeignKey("needs.id", ondelete="CASCADE"), nullable=False, index=True)
    query_filters_hash = Column(String(64), nullable=True)
    ranked_candidates_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    need = relationship("Need", back_populates="selection_snapshots")
    shortlist_items = relationship("ShortlistItem", back_populates="snapshot", cascade="all, delete-orphan")


class ShortlistItem(Base):
    __tablename__ = "shortlist_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_id = Column(String(36), ForeignKey("selection_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Float, nullable=False, default=0.0)
    rank = Column(Integer, nullable=False, default=1)
    explanation = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    snapshot = relationship("SelectionSnapshot", back_populates="shortlist_items")
    candidate_profile = relationship("CandidateProfile", back_populates="shortlist_items")


class Vacancy(Base):
    __tablename__ = "vacancies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    need_id = Column(String(36), ForeignKey("needs.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    specialization = Column(String(100), nullable=False)
    grade = Column(String(50), nullable=False)
    salary_min = Column(Integer, nullable=False)  # in RUB
    salary_max = Column(Integer, nullable=False)  # in RUB
    salary_type = Column(String(20), default="NET", nullable=False)  # NET (на руки), GROSS (до вычета)
    is_gross = Column(Boolean, default=False, nullable=False)
    work_format = Column(String(50), default="REMOTE", nullable=True)
    city = Column(String(100), default="Москва", nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    company = relationship("Company", back_populates="vacancies")


class EmployerChallenge(Base):
    __tablename__ = "employer_challenges"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    task_description = Column(Text, nullable=False)
    specialization = Column(String(100), nullable=False)
    target_grade = Column(String(50), nullable=False)
    task_type = Column(String(50), default="CODE_REVIEW", nullable=False)
    time_limit_minutes = Column(Integer, default=30, nullable=False)
    status = Column(String(50), default="ACTIVE", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    company = relationship("Company", back_populates="challenges")
    submissions = relationship("EmployerChallengeSubmission", back_populates="challenge", cascade="all, delete-orphan")


class EmployerChallengeSubmission(Base):
    __tablename__ = "employer_challenge_submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    challenge_id = Column(String(36), ForeignKey("employer_challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    answer_text = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    status = Column(String(50), default="SUBMITTED", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)

    challenge = relationship("EmployerChallenge", back_populates="submissions")
    candidate_profile = relationship("CandidateProfile")
