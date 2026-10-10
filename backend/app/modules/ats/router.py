"""ATS Integration and Beyond MVP Endpoints Router.

Provides working endpoints and OpenAPI contracts for:
- ATS Synchronization (Huntflow, Potok, E-Staff): a vacancy from the employer's ATS becomes a need of their company
- Candidate Profile Export for Corporate ATS (no contacts, only data the platform actually holds)
- Company INN check (checksum; the ЕГРЮЛ lookup is part of the anti-fraud concept, not of the MVP)
- Regular Employer Challenges and Micro-Tasks (TOR 2.1 & Q&A Row 2): the employer publishes a short task,
  candidates answer it, the employer reads the answers. An answer refreshes the candidate's profile activity.
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from backend.app.core.database import get_db
    from backend.app.models.candidate import CandidateProfile
    from backend.app.models.company import Company, EmployerChallenge, EmployerChallengeSubmission, Need
    from backend.app.modules.auth.service import get_current_candidate, get_current_company, require_employer
except ImportError:
    from app.core.database import get_db
    from app.models.candidate import CandidateProfile
    from app.models.company import Company, EmployerChallenge, EmployerChallengeSubmission, Need
    from app.modules.auth.service import get_current_candidate, get_current_company, require_employer

router = APIRouter(prefix="", tags=["ATS & Employer Challenges (Beyond MVP)"])


# ==========================================
# SCHEMAS
# ==========================================

class ATSVacancySyncRequest(BaseModel):
    ats_system: str = Field(..., description="Система ATS источника: HUNTFLOW, POTOK, E_STAFF, CUSTOM")
    external_vacancy_id: str = Field(..., description="Идентификатор вакансии во внешней ATS")
    title: str = Field(..., description="Название должности")
    specialization: str = Field(..., description="Специализация (BACKEND, FRONTEND, QA, DATA_ML, DEVOPS)")
    target_grade: str = Field(..., description="Требуемый грейд (JUNIOR, MIDDLE, SENIOR)")
    salary_min: int = Field(..., gt=0, description="Гарантированный зарплатный бюджет от (в рублях)")
    salary_max: int = Field(..., gt=0, description="Зарплатный бюджет до (в рублях)")
    salary_type: str = Field("NET", description="Тип зарплаты: NET или GROSS")
    required_skills: list[str] = Field(default_factory=list, description="Требуемые ключевые навыки")
    description: str | None = Field(None, description="Текст описания вакансии")
    webhook_url: str | None = Field(None, description="URL для отправки обратных вебхуков о статусах")


class ATSVacancySyncResponse(BaseModel):
    success: bool
    need_id: str
    ats_system: str
    external_vacancy_id: str
    sync_status: str = "SYNCHRONIZED"
    message: str


class ATSCandidateExportResponse(BaseModel):
    candidate_id: str
    full_name: str | None
    confirmed_category: str | None
    confirmed_grade: str | None
    category_percentile: int | None
    fsp_score: float
    is_fsp_verified: bool
    verified_skills: list[str]
    pdf_passport_url: str
    exported_at: str


class CompanyVerifyINNRequest(BaseModel):
    inn: str = Field(..., description="ИНН организации (10 знаков для юрлиц, 12 знаков для ИП)")
    ogrn: str | None = Field(None, description="ОГРН юридического лица (13 или 15 знаков)")


class CompanyVerifyINNResponse(BaseModel):
    success: bool
    inn: str
    is_valid_inn: bool
    organization_status: str
    verification_tier: str
    is_disqualified: bool = False
    in_unscrupulous_suppliers_registry: bool = False
    trust_score: int
    message: str


class EmployerChallengeCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, description="Название короткого задания (например: 'Оптимизация N+1 в ORM')")
    task_description: str = Field(..., min_length=10, description="Формулировка задачи или архитектурного кейса")
    specialization: str = Field(..., description="Специализация (BACKEND, FRONTEND, QA, DATA_ML)")
    target_grade: str = Field(..., description="Целевой грейд (JUNIOR, MIDDLE, SENIOR)")
    task_type: str = Field("CODE_REVIEW", description="Тип задания: CODE_REVIEW, ARCHITECTURE, ALGORITHM, OPEN_ENDED")
    time_limit_minutes: int = Field(30, ge=5, le=240, description="Рекомендуемое время решения в минутах")


class EmployerChallengeItem(BaseModel):
    id: str
    company_name: str
    title: str
    task_description: str
    specialization: str
    target_grade: str
    task_type: str
    time_limit_minutes: int
    status: str = "ACTIVE"
    created_at: str
    submissions_count: int = Field(0, description="Сколько кандидатов ответили (для работодателя)")
    my_answer: str | None = Field(None, description="Ответ текущего кандидата, если он уже отвечал")
    submitted_at: str | None = Field(None, description="Когда кандидат отправил ответ")


class ChallengeSubmissionItem(BaseModel):
    id: str
    candidate_profile_id: str
    candidate_name: str
    confirmed_category: str | None = None
    is_grade_confirmed: bool = False
    answer_text: str | None = None
    status: str
    submitted_at: str


class ChallengeSubmitRequest(BaseModel):
    solution_text: str = Field(..., min_length=10, max_length=10000, description="Текст решения или ссылка на репозиторий")


# ==========================================
# ATS
# ==========================================

@router.post("/ats/vacancies/sync", response_model=ATSVacancySyncResponse)
def sync_ats_vacancy(
    payload: ATSVacancySyncRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Вакансия из ATS работодателя становится потребностью его компании и сразу участвует в подборе."""
    if payload.salary_min > payload.salary_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="salary_min не может быть больше salary_max",
        )
    salary_type = payload.salary_type.strip().upper()
    if salary_type not in ("NET", "GROSS"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="salary_type: NET или GROSS")

    need = Need(
        company_id=company.id,
        title=payload.title,
        target_specialization=payload.specialization,
        target_grade=payload.target_grade,
        required_skills=payload.required_skills,
        raw_description=payload.description,
        salary_budget_min=payload.salary_min,
        salary_budget_max=payload.salary_max,
        salary_type=salary_type,
        is_gross=salary_type == "GROSS",
        work_format="REMOTE",
        is_active=True,
    )
    db.add(need)
    db.commit()
    db.refresh(need)

    return ATSVacancySyncResponse(
        success=True,
        need_id=need.id,
        ats_system=payload.ats_system.upper(),
        external_vacancy_id=payload.external_vacancy_id,
        sync_status="SYNCHRONIZED",
        message=f"Вакансия '{payload.title}' импортирована из {payload.ats_system} и включена в пул подбора.",
    )


@router.post(
    "/ats/candidates/{candidate_id}/export",
    response_model=ATSCandidateExportResponse,
    dependencies=[Depends(require_employer)],
)
def export_candidate_to_ats(candidate_id: str, db: Session = Depends(get_db)):
    """Карточка кандидата для ATS работодателя: подтверждённая категория и навыки из профиля, без контактов."""
    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_id).first()
    if not candidate or candidate.status == "HIDDEN":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кандидат не найден",
        )

    full_name_val = f"{candidate.first_name or ''} {candidate.last_name or ''}".strip() or None
    skills = [cs.skill.name for cs in candidate.skills if cs.skill is not None]

    return ATSCandidateExportResponse(
        candidate_id=candidate.id,
        full_name=full_name_val,
        confirmed_category=candidate.confirmed_category,
        confirmed_grade=candidate.confirmed_grade,
        category_percentile=candidate.category_percentile,
        fsp_score=float(candidate.fsp_score or 0.0),
        is_fsp_verified=bool(candidate.is_fsp_verified),
        verified_skills=skills,
        pdf_passport_url=f"/api/v1/candidates/{candidate.id}/pdf",
        exported_at=datetime.now(timezone.utc).isoformat(),
    )


# ==========================================
# COMPANY INN CHECK
# ==========================================

def _check_inn_checksum(inn: str) -> bool:
    """Валидирует контрольные суммы ИНН юрлица (10 знаков) или ИП (12 знаков)."""
    if not re.match(r"^\d{10}$|^\d{12}$", inn):
        return False
    digits = [int(c) for c in inn]
    if len(inn) == 10:
        coeffs = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        control = sum(d * c for d, c in zip(digits[:9], coeffs)) % 11 % 10
        return control == digits[9]
    elif len(inn) == 12:
        coeffs1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        control1 = sum(d * c for d, c in zip(digits[:10], coeffs1)) % 11 % 10
        coeffs2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        control2 = sum(d * c for d, c in zip(digits[:11], coeffs2)) % 11 % 10
        return control1 == digits[10] and control2 == digits[11]
    return False


@router.post("/companies/{company_id}/verify-inn", response_model=CompanyVerifyINNResponse)
def verify_company_inn(
    company_id: str,
    payload: CompanyVerifyINNRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Проверка ИНН своей компании: формат и контрольная сумма.

    Это первая ступень защиты от фиктивных вакансий. Запрос в ЕГРЮЛ (статус организации, дисквалификации,
    реестр недобросовестных поставщиков) — часть концепции после MVP: в демо он не выполняется.
    """
    if company_id != company.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Проверить можно только свою компанию.")
    clean_inn = payload.inn.strip()
    if not _check_inn_checksum(clean_inn):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный формат или контрольная сумма ИНН",
        )

    company.is_verified = True
    company.inn = clean_inn
    db.commit()

    return CompanyVerifyINNResponse(
        success=True,
        inn=clean_inn,
        is_valid_inn=True,
        organization_status="ИНН корректен (запрос в ЕГРЮЛ в демо не выполняется)",
        verification_tier="INN_CHECKSUM",
        is_disqualified=False,
        in_unscrupulous_suppliers_registry=False,
        trust_score=60,
        message="Контрольная сумма ИНН верна: кандидаты видят отметку «ИНН проверен».",
    )


# ==========================================
# REGULAR EMPLOYER CHALLENGES
# ==========================================

def _challenge_item(c: EmployerChallenge, submissions_count: int = 0,
                    mine: EmployerChallengeSubmission | None = None) -> EmployerChallengeItem:
    return EmployerChallengeItem(
        id=c.id,
        company_name=c.company.name if c.company else "",
        title=c.title,
        task_description=c.task_description,
        specialization=c.specialization,
        target_grade=c.target_grade,
        task_type=c.task_type,
        time_limit_minutes=c.time_limit_minutes,
        status=c.status,
        created_at=c.created_at.isoformat(),
        submissions_count=submissions_count,
        my_answer=mine.answer_text if mine else None,
        submitted_at=mine.created_at.isoformat() if mine else None,
    )


@router.get("/candidates/me/challenges", response_model=list[EmployerChallengeItem])
def get_candidate_challenges(
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Активные регулярные задания работодателей (п. 2.1 ТЗ, Q&A Row 2): сначала по специализации кандидата.
    Для заданий, на которые кандидат уже ответил, возвращается его ответ."""
    challenges = (
        db.query(EmployerChallenge)
        .filter(EmployerChallenge.status == "ACTIVE")
        .order_by(EmployerChallenge.created_at.desc())
        .all()
    )
    own_spec = (candidate.confirmed_specialization or "").strip().upper()
    challenges.sort(key=lambda c: c.specialization.strip().upper() != own_spec)  # stable: own specialization first
    mine = {
        s.challenge_id: s
        for s in db.query(EmployerChallengeSubmission)
        .filter(EmployerChallengeSubmission.candidate_profile_id == candidate.id)
        .all()
    }
    return [_challenge_item(c, mine=mine.get(c.id)) for c in challenges]


@router.post("/challenges/{challenge_id}/submit")
def submit_challenge_solution(
    challenge_id: str,
    payload: ChallengeSubmitRequest,
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Ответ кандидата на регулярное задание. Повторная отправка заменяет ответ.
    Ответ обновляет актуальность профиля (компонент A ранжирования)."""
    challenge = db.query(EmployerChallenge).filter(EmployerChallenge.id == challenge_id).first()
    if not challenge or challenge.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задание не найдено или закрыто.")

    submission = (
        db.query(EmployerChallengeSubmission)
        .filter(
            EmployerChallengeSubmission.challenge_id == challenge.id,
            EmployerChallengeSubmission.candidate_profile_id == candidate.id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if submission:
        submission.answer_text = payload.solution_text
        submission.status = "SUBMITTED"
        submission.created_at = now
    else:
        db.add(EmployerChallengeSubmission(
            challenge_id=challenge.id,
            candidate_profile_id=candidate.id,
            answer_text=payload.solution_text,
            status="SUBMITTED",
            created_at=now,
        ))
    candidate.updated_at = now  # fresh activity signal for the employer's ranking
    db.commit()

    return {
        "success": True,
        "challenge_id": challenge.id,
        "status": "UNDER_REVIEW",
        "message": f"Ответ передан компании «{challenge.company.name}». Его оценивает работодатель.",
    }


@router.post("/challenges", response_model=EmployerChallengeItem)
def create_employer_challenge(
    payload: EmployerChallengeCreateRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Работодатель публикует короткое задание от имени своей компании."""
    challenge = EmployerChallenge(
        company_id=company.id,
        title=payload.title,
        task_description=payload.task_description,
        specialization=payload.specialization.strip().upper(),
        target_grade=payload.target_grade.strip().upper(),
        task_type=payload.task_type,
        time_limit_minutes=payload.time_limit_minutes,
        status="ACTIVE",
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return _challenge_item(challenge)


@router.get("/employer/challenges", response_model=list[EmployerChallengeItem])
def list_employer_challenges(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Задания компании текущего работодателя с числом полученных ответов."""
    challenges = (
        db.query(EmployerChallenge)
        .filter(EmployerChallenge.company_id == company.id)
        .order_by(EmployerChallenge.created_at.desc())
        .all()
    )
    counts = dict(
        db.query(EmployerChallengeSubmission.challenge_id, func.count(EmployerChallengeSubmission.id))
        .filter(EmployerChallengeSubmission.challenge_id.in_([c.id for c in challenges]))
        .group_by(EmployerChallengeSubmission.challenge_id)
        .all()
    )
    return [_challenge_item(c, submissions_count=counts.get(c.id, 0)) for c in challenges]


@router.get("/employer/challenges/{challenge_id}/submissions", response_model=list[ChallengeSubmissionItem])
def list_challenge_submissions(
    challenge_id: str,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Ответы кандидатов на задание своей компании: имя и категория кандидата, без контактов."""
    challenge = db.query(EmployerChallenge).filter(EmployerChallenge.id == challenge_id).first()
    if not challenge or challenge.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задание не найдено.")
    submissions = (
        db.query(EmployerChallengeSubmission)
        .filter(EmployerChallengeSubmission.challenge_id == challenge.id)
        .order_by(EmployerChallengeSubmission.created_at.desc())
        .all()
    )
    items = []
    for s in submissions:
        cand = s.candidate_profile
        name = f"{cand.first_name or ''} {cand.last_name or ''}".strip() if cand else ""
        items.append(ChallengeSubmissionItem(
            id=s.id,
            candidate_profile_id=s.candidate_profile_id,
            candidate_name=name or f"Кандидат #{s.candidate_profile_id[:8]}",
            confirmed_category=cand.confirmed_category if cand and cand.confirmed_grade else None,
            is_grade_confirmed=bool(cand and cand.confirmed_grade),
            answer_text=s.answer_text,
            status=s.status,
            submitted_at=s.created_at.isoformat(),
        ))
    return items
