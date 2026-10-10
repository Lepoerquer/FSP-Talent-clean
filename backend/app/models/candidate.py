import uuid
from datetime import datetime, timezone

from sqlalchemy import (
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


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # Personal & contact info (protected by 152-FZ contact anonymization)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    telegram = Column(String(100), nullable=True)
    fsp_id = Column(String(100), nullable=True, index=True)
    
    # Candidate status & qualification
    status = Column(String(50), default="ACTIVELY_SEARCHING", nullable=False)  # ACTIVELY_SEARCHING, OPEN, HIDDEN
    confirmed_category = Column(String(150), nullable=True)  # Specialization x Grade, e.g. "Backend · Middle"
    confirmed_specialization = Column(String(100), nullable=True)
    confirmed_grade = Column(String(50), nullable=True)
    declared_grade = Column(String(50), nullable=True)  # Self-declared or target grade before/during assessment

    @property
    def is_grade_confirmed(self) -> bool:
        return bool(self.confirmed_grade)

    @property
    def grade_status(self) -> str:
        return "CONFIRMED" if self.confirmed_grade else "UNCONFIRMED"

    @property
    def grade_status_display(self) -> str:
        return "Подтверждён" if self.confirmed_grade else "Не подтверждён"
    
    # IRT / CAT assessment metrics
    last_theta = Column(Float, default=0.0, nullable=False)  # IRT latent ability estimate
    last_se = Column(Float, default=1.0, nullable=False)     # Standard error of estimation
    category_percentile = Column(Integer, default=None, nullable=True)  # Set by the test; empty until one is finished
    
    # FSP Federation achievements score (0.0 .. 1.0)
    fsp_score = Column(Float, default=0.0, nullable=False)
    
    # Preferences
    desired_salary_min = Column(Integer, nullable=True)  # In RUB
    salary_type = Column(String(20), default="NET", nullable=False)  # NET (на руки), GROSS (до вычета НДФЛ)
    is_gross = Column(Boolean, default=False, nullable=False)
    work_format = Column(String(50), default="REMOTE", nullable=True)  # REMOTE, HYBRID, OFFICE
    city = Column(String(100), default="Москва", nullable=True)
    
    # Verification & privacy flags
    is_fsp_verified = Column(Boolean, default=False, nullable=False)
    hide_contacts_globally = Column(Boolean, default=True, nullable=False)  # Contacts revealed only upon ACCEPTED invitation
    next_grade_change_available_at = Column(DateTime, nullable=True)  # 90 days cooldown for grade retake
    
    # Extended profile fields
    experience_years = Column(Float, nullable=True)
    stack = Column(Text, nullable=True)
    soft_skills = Column(Text, nullable=True)
    roles = Column(Text, nullable=True)
    about_me = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="candidate_profile")
    skills = relationship("CandidateSkill", back_populates="candidate_profile", cascade="all, delete-orphan")
    specializations = relationship("CandidateSpecialization", back_populates="candidate_profile", cascade="all, delete-orphan")
    assessment_sessions = relationship("AssessmentSession", back_populates="candidate_profile", cascade="all, delete-orphan")
    grade_history = relationship("GradeHistory", back_populates="candidate_profile", cascade="all, delete-orphan")
    fsp_achievements = relationship("FSPAchievement", back_populates="candidate_profile", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="candidate_profile", cascade="all, delete-orphan")
    shortlist_items = relationship("ShortlistItem", back_populates="candidate_profile", cascade="all, delete-orphan")


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    confirmation_source = Column(String(50), default="CLAIMED", nullable=False)  # CLAIMED, RESUME, ASSESSMENT, FSP
    weight = Column(Float, default=1.0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    candidate_profile = relationship("CandidateProfile", back_populates="skills")
    skill = relationship("Skill")


class CandidateSpecialization(Base):
    __tablename__ = "candidate_specializations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    specialization = Column(String(100), nullable=False)
    grade = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    candidate_profile = relationship("CandidateProfile", back_populates="specializations")


class GradeHistory(Base):
    __tablename__ = "grade_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_grade = Column(String(50), nullable=True)
    new_grade = Column(String(50), nullable=False)
    specialization = Column(String(100), nullable=False)
    reason = Column(String(100), default="ASSESSMENT", nullable=False)  # ASSESSMENT, INITIAL_REGISTRATION, MANUAL_RECHECK
    assessment_session_id = Column(String(36), nullable=True)
    changed_at = Column(DateTime, default=utcnow, nullable=False)

    candidate_profile = relationship("CandidateProfile", back_populates="grade_history")


class FSPAchievement(Base):
    __tablename__ = "fsp_achievements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    event_name = Column(String(255), nullable=False)
    event_date = Column(DateTime, nullable=True)
    discipline = Column(String(100), default="Спортивное программирование", nullable=False)
    level = Column(String(50), default="ALL_RUSSIAN", nullable=False)  # REGIONAL, INTERREGIONAL, ALL_RUSSIAN, INTERNATIONAL
    result = Column(String(50), default="PARTICIPANT", nullable=False)  # WINNER, PRIZE_WINNER, FINALIST, PARTICIPANT
    sport_category = Column(String(50), nullable=True)  # КМС, Мастер спорта, 1 разряд, etc.
    calculated_weight = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    candidate_profile = relationship("CandidateProfile", back_populates="fsp_achievements")
