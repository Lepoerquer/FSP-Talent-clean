import uuid

from sqlalchemy import JSON, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.app.core.database import Base


class Direction(Base):
    __tablename__ = "directions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)  # Разработка, Data & ML, Тестирование, Инфраструктура

    specializations = relationship("Specialization", back_populates="direction")


class Specialization(Base):
    __tablename__ = "specializations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    direction_id = Column(String(36), ForeignKey("directions.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)  # Backend, Frontend, QA Engineer, Data Scientist / ML
    has_active_assessment = Column(Integer, default=1)  # 1 for MVP with test, 0 for dictionary-only

    direction = relationship("Direction", back_populates="specializations")
    categories = relationship("Category", back_populates="specialization")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, nullable=False)  # INTERN, JUNIOR, MIDDLE, SENIOR
    name = Column(String(100), nullable=False)
    rank = Column(Integer, nullable=False)  # 1, 2, 3, 4
    behavioral_indicators = Column(JSON, nullable=True)  # List of behavioral indicators

    categories = relationship("Category", back_populates="grade")


class Category(Base):
    __tablename__ = "categories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    specialization_id = Column(String(36), ForeignKey("specializations.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(String(36), ForeignKey("grades.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(100), unique=True, nullable=False)  # e.g. BACKEND_MIDDLE
    display_name = Column(String(150), nullable=False)  # e.g. "Backend · Middle"

    specialization = relationship("Specialization", back_populates="categories")
    grade = relationship("Grade", back_populates="categories")


class Skill(Base):
    __tablename__ = "skills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(100), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    category_tags = Column(JSON, nullable=True)  # ["backend", "database", "python"]

    synonyms = relationship("SkillSynonym", back_populates="skill")


class SkillSynonym(Base):
    __tablename__ = "skill_synonyms"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    synonym = Column(String(150), index=True, nullable=False)  # "постгрес" -> PostgreSQL

    skill = relationship("Skill", back_populates="synonyms")
