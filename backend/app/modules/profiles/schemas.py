"""Pydantic schemas for candidate profile, company profile, and PDF exports."""

from datetime import datetime

from pydantic import BaseModel, Field


class CandidateSkillInfo(BaseModel):
    id: str
    skill_id: str
    name: str
    code: str
    confirmation_source: str
    weight: float = 1.0


class CandidateFSPAchievementInfo(BaseModel):
    id: str
    event_name: str
    discipline: str
    level: str
    result: str
    sport_category: str | None = None
    event_date: str | None = None


class CandidateProfileResponse(BaseModel):
    id: str
    user_id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    city: str | None = None
    work_format: str | None = None
    desired_salary_min: int | None = None
    salary_type: str = "NET"
    is_gross: bool = False
    salary_display: str | None = None
    status: str = "ACTIVELY_SEARCHING"
    confirmed_category: str | None = None
    confirmed_specialization: str | None = None
    confirmed_grade: str | None = None
    is_grade_confirmed: bool = True
    grade_status: str = "CONFIRMED"
    grade_status_display: str = "Подтверждён"
    declared_grade: str | None = None
    category_percentile: int | None = None
    last_theta: float = 0.0
    last_se: float = 1.0
    fsp_id: str | None = None
    fsp_score: float = 0.0
    is_fsp_verified: bool = False
    hide_contacts_globally: bool = True
    skills: list[CandidateSkillInfo] = Field(default_factory=list)
    fsp_achievements: list[CandidateFSPAchievementInfo] = Field(default_factory=list)
    experience_years: float | None = None
    stack: str | None = None
    soft_skills: str | None = None
    roles: str | None = None
    about_me: str | None = None
    created_at: str
    updated_at: str


class CandidateProfileUpdateRequest(BaseModel):
    first_name: str | None = Field(None, description="Имя")
    last_name: str | None = Field(None, description="Фамилия")
    phone: str | None = Field(None, description="Номер телефона (+7...)")
    telegram: str | None = Field(None, description="Никнейм в Telegram (@...)")
    city: str | None = Field(None, description="Город проживания")
    work_format: str | None = Field(None, description="Формат работы (REMOTE, HYBRID, OFFICE)")
    desired_salary_min: int | None = Field(None, description="Ожидаемая заработная плата в рублях")
    salary_type: str | None = Field(None, description="Тип зарплаты (NET — на руки, GROSS — до вычета НДФЛ)")
    is_gross: bool | None = Field(None, description="Флаг: True если до вычета НДФЛ (Гросс), False если на руки (Нетто)")
    status: str | None = Field(None, description="Статус поиска (ACTIVELY_SEARCHING, OPEN, HIDDEN)")
    experience_years: float | None = Field(None, description="Опыт работы в годах")
    stack: str | None = Field(None, description="Технологический стек")
    soft_skills: str | None = Field(None, description="Soft skills")
    roles: str | None = Field(None, description="Роли")
    about_me: str | None = Field(None, description="О себе")


class CandidateVerificationResponse(BaseModel):
    """Public check of a PDF profile: what the platform holds right now, without contacts."""
    candidate_id: str
    name: str = Field(..., description="Имя и инициал фамилии для сверки с PDF")
    confirmed_category: str | None = Field(None, description="Категория, подтверждённая тестом")
    grade_status: str = Field(..., description="CONFIRMED или UNCONFIRMED")
    is_fsp_verified: bool = Field(False, description="Достижения привязаны из реестра ФСП")
    category_percentile: int | None = Field(None, description="Перцентиль среди специалистов категории")
    confirmed_specialization: str | None = Field(None, description="Специализация")
    confirmed_grade: str | None = Field(None, description="Подтверждённый грейд")
    declared_grade: str | None = Field(None, description="Заявленный грейд, если не подтверждён")
    city: str | None = Field(None, description="Город")
    work_format: str | None = Field(None, description="Формат работы")
    experience_years: float | None = Field(None, description="Опыт работы")
    confirmed_skills: list[str] = Field(default_factory=list, description="Подтверждённые навыки")
    fsp_achievements_count: int = Field(0, description="Количество соревнований ФСП")
    fsp_disciplines: list[str] = Field(default_factory=list, description="Дисциплины ФСП")
    verification_hash: str | None = Field(None, description="Контрольный хэш верификации")
    checked_at: datetime


class CompanyResponse(BaseModel):
    id: str
    name: str
    inn: str | None = None
    website: str | None = None
    description: str | None = None
    logo_url: str | None = None
    is_verified: bool = False
    direction: str | None = None
    contacts: str | None = None
    created_at: str


class CompanyUpdateRequest(BaseModel):
    name: str | None = Field(None, description="Название компании")
    inn: str | None = Field(None, description="ИНН компании")
    website: str | None = Field(None, description="Сайт компании")
    description: str | None = Field(None, description="Описание компании и деятельности")
    logo_url: str | None = Field(None, description="URL логотипа")
    direction: str | None = Field(None, description="Направление")
    contacts: str | None = Field(None, description="Контакты")
