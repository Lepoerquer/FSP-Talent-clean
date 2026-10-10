"""Schemas for invitations, salary validation, state transitions and contact disclosure."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class InvitationStatusEnum(str, Enum):
    SENT = "SENT"
    APPLIED = "APPLIED"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    CONTACTS_REVOKED = "CONTACTS_REVOKED"


class DeclineReasonEnum(str, Enum):
    SALARY = "SALARY"
    TECH_STACK = "TECH_STACK"
    FORMAT = "FORMAT"
    NOT_LOOKING = "NOT_LOOKING"
    OTHER = "OTHER"


class ContactMethodEnum(str, Enum):
    TELEGRAM = "TELEGRAM"
    EMAIL = "EMAIL"
    PHONE = "PHONE"


class InvitationCreate(BaseModel):
    candidate_profile_id: str = Field(
        ...,
        description="Идентификатор профиля кандидата, которому направляется оффер/приглашение",
    )
    company_id: str | None = Field(
        None,
        description="Идентификатор компании-работодателя (если не извлечен из сессии/токена)",
    )
    need_id: str | None = Field(
        None,
        description="Идентификатор потребности/вакансии, по которой отправляется приглашение",
    )
    salary_from: int = Field(
        ...,
        description="Гарантированная нижняя граница оклада в рублях (RUB) — строго > 0",
    )
    salary_to: int = Field(
        ...,
        description="Верхняя граница оклада в рублях (RUB) — строго >= salary_from",
    )
    salary_type: str | None = Field(
        default="NET",
        description="Тип оклада: NET ('на руки') или GROSS ('до вычета НДФЛ')",
    )
    is_gross: bool = Field(
        default=False,
        description="True если оклад указан до вычета НДФЛ (Гросс), False если на руки (Нетто)",
    )
    message: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Персонализированное сообщение работодателя (описание роли, проекта и условий)",
    )
    contact_method: str = Field(
        default="TELEGRAM",
        description="Предпочитаемый способ связи после раскрытия контактов (TELEGRAM, EMAIL, PHONE)",
    )

    @model_validator(mode="after")
    def validate_salary_range(self) -> "InvitationCreate":
        if self.salary_from <= 0:
            raise ValueError("Зарплата 'от' (salary_from) должна быть строго положительной (больше 0 рублей).")
        if self.salary_to <= 0:
            raise ValueError("Зарплата 'до' (salary_to) должна быть строго больше 0 рублей.")
        if self.salary_from > self.salary_to:
            raise ValueError(
                f"Минимальная зарплата {self.salary_from:,} руб. не может превышать "
                f"максимальную {self.salary_to:,} руб."
            )
        return self


class InvitationStatusTransitionRequest(BaseModel):
    decline_reason: DeclineReasonEnum | None = Field(
        None,
        description="Причина отказа (обязательна при переходе в статус DECLINED: SALARY, TECH_STACK, FORMAT, NOT_LOOKING)",
    )
    feedback: str | None = Field(
        None,
        max_length=1000,
        description="Необязательный комментарий кандидата или работодателя при смене статуса",
    )


class CompanyShortInfo(BaseModel):
    id: str
    name: str
    inn: str | None = None
    website: str | None = None
    logo_url: str | None = None
    is_verified: bool = False


class CandidateDisclosedContacts(BaseModel):
    """Контактные данные: раскрываются после принятия приглашения или собственного отклика кандидата (152-ФЗ)."""
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    telegram: str | None = None
    email: str | None = None
    disclosed_at: datetime | None = None


class CandidateAnonymizedCard(BaseModel):
    """Анонимизированная карточка кандидата до принятия приглашения."""
    id: str
    full_name: str | None = None
    confirmed_category: str | None = None
    confirmed_specialization: str | None = None
    confirmed_grade: str | None = None
    is_grade_confirmed: bool = True
    grade_status: str = "CONFIRMED"
    category_percentile: int | None = None
    fsp_score: float = 0.0
    is_fsp_verified: bool = False
    desired_salary_min: int | None = None
    salary_type: str = "NET"
    is_gross: bool = False
    salary_display: str | None = None
    work_format: str | None = None
    city: str | None = None
    contacts_hidden: bool = True


class InvitationResponse(BaseModel):
    id: str
    company_id: str
    candidate_profile_id: str
    need_id: str | None = None
    status: str
    salary_from: int
    salary_to: int
    salary_currency: str = "RUB"
    salary_type: str = "NET"
    is_gross: bool = False
    salary_display: str | None = None
    message: str
    contact_method: str
    decline_reason: str | None = None
    sent_at: datetime
    viewed_at: datetime | None = None
    resolved_at: datetime | None = None
    expires_at: datetime
    is_expired: bool = False

    # Вложенная информация
    company: CompanyShortInfo | None = None
    candidate_card: CandidateAnonymizedCard | None = None

    # Контакты раскрываются при status == ACCEPTED (приглашение принято) или APPLIED (кандидат откликнулся сам)
    candidate_contacts: CandidateDisclosedContacts | None = None
    contacts_disclosed: bool = False
