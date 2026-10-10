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
from sqlalchemy.orm import relationship, synonym

try:
    from backend.app.core.database import Base
except ImportError:
    from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ItemFamily(Base):
    __tablename__ = "item_families"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(100), unique=True, nullable=False, index=True)
    specialization = Column(String(100), nullable=False, index=True)
    target_grade = Column(String(50), nullable=False, index=True)
    topic = Column(String(100), nullable=False)
    item_format = Column(String(50), nullable=False)  # CODE_OUTPUT, CODE_ERROR, SQL, COMPLEXITY, MCQ
    
    # IRT 2PL item calibration parameters
    discrimination_a = Column(Float, default=1.0, nullable=False)  # Slope parameter
    difficulty_b = Column(Float, default=0.0, nullable=False)      # Location / difficulty parameter
    
    # Exposure control (Sympson-Hetter / maximum 25% exposure rate)
    exposure_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Isomorphic template in YAML format
    template_yaml = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    session_items = relationship("SessionItem", back_populates="item_family")


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_profile_id = Column(String(36), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    specialization = Column(String(100), nullable=False)
    target_grade = Column(String(50), nullable=False)
    
    # Adaptive CAT state
    current_theta = Column(Float, default=0.0, nullable=False)
    current_se = Column(Float, default=1.0, nullable=False)
    status = Column(String(50), default="IN_PROGRESS", nullable=False)  # IN_PROGRESS, COMPLETED, TIMED_OUT, FLAGGED
    items_count = Column(Integer, default=0, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)  # Demo/express mode for jury (5 items)
    
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    candidate_profile = relationship("CandidateProfile", back_populates="assessment_sessions")
    session_items = relationship("SessionItem", back_populates="session", cascade="all, delete-orphan", order_by="SessionItem.presented_at")


class SessionItem(Base):
    __tablename__ = "session_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    item_family_id = Column(String(36), ForeignKey("item_families.id", ondelete="CASCADE"), nullable=False, index=True)
    
    seed = Column(Integer, nullable=False)
    rendered_question = Column(Text, nullable=False)
    user_response = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    response_time_seconds = Column(Float, nullable=True)
    
    presented_at = Column(DateTime, default=utcnow, nullable=False)
    answered_at = Column(DateTime, nullable=True)

    # Synonyms / property aliases for code flexibility
    question = synonym("rendered_question")
    response = synonym("user_response")
    response_time = synonym("response_time_seconds")

    session = relationship("AssessmentSession", back_populates="session_items")
    item_family = relationship("ItemFamily", back_populates="session_items")
