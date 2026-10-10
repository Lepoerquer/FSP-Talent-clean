"""FastAPI Router for Employer Needs, Explainable Recommendations, and Candidate Search."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.llm import llm_client
from backend.app.models.candidate import CandidateProfile
from backend.app.models.company import Company, Need, SelectionSnapshot
from backend.app.models.invitation import Invitation, InvitationStatus
from backend.app.modules.auth.service import get_current_candidate, get_current_company, require_employer
from backend.app.modules.matching.need_parser import parse_need_hybrid
from backend.app.modules.matching.ranking import execute_two_stage_matching
from backend.app.modules.matching.snapshots import SelectionSnapshotService

router = APIRouter(tags=["Matching & Recommendations"])


# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

class NeedCreateRequest(BaseModel):
    title: str = Field(..., description="Название потребности / позиции (например, 'Senior Python Backend-разработчик')")
    target_specialization: str = Field(..., description="Целевая специализация (Backend, Frontend, QA, Data Scientist, DevOps)")
    target_grade: str = Field(..., description="Требуемый грейд (JUNIOR, MIDDLE, SENIOR, LEAD)")
    required_skills: list[str] = Field(default_factory=list, description="Список обязательных или ключевых навыков")
    raw_description: str | None = Field(None, description="Полный текст описания вакансии/задачи")
    salary_budget_min: int | None = Field(None, description="Нижняя граница бюджета в рублях")
    salary_budget_max: int | None = Field(None, description="Верхняя граница бюджета в рублях")
    salary_type: str | None = Field("NET", description="Тип бюджета: NET ('на руки') или GROSS ('до вычета НДФЛ')")
    is_gross: bool | None = Field(False, description="True если бюджет указан до вычета НДФЛ (Гросс), False если на руки (Нетто)")
    work_format: str | None = Field("REMOTE", description="Формат работы (REMOTE, HYBRID, OFFICE)")
    company_id: str | None = Field(None, description="Устарело: компания берётся из токена работодателя")

class NeedUpdateRequest(BaseModel):
    title: str | None = Field(None, description="Название потребности")
    target_specialization: str | None = Field(None, description="Целевая специализация")
    target_grade: str | None = Field(None, description="Требуемый грейд")
    required_skills: list[str] | None = Field(None, description="Список навыков")
    raw_description: str | None = Field(None, description="Текст описания")
    salary_budget_min: int | None = Field(None, description="Нижняя граница бюджета")
    salary_budget_max: int | None = Field(None, description="Верхняя граница бюджета")
    salary_type: str | None = Field(None, description="Тип бюджета")
    is_gross: bool | None = Field(None, description="Гросс")
    work_format: str | None = Field(None, description="Формат работы")
    is_active: bool | None = Field(None, description="Активна ли вакансия")


class NeedResponse(BaseModel):
    id: str
    full_name: str | None = None
    company_id: str
    company_name: str | None = None
    company_is_verified: bool = False
    title: str
    target_specialization: str
    target_grade: str
    required_skills: list[str]
    raw_description: str | None = None
    salary_budget_min: int | None = None
    salary_budget_max: int | None = None
    salary_type: str = "NET"
    is_gross: bool = False
    salary_display: str | None = None
    work_format: str | None = None
    is_active: bool
    created_at: str


class NeedParseRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=20000, description="Свободный текст потребности или вакансии")
    title: str | None = Field(None, max_length=300, description="Заголовок вакансии, если есть")
    provider: str | None = Field("auto", description="Провайдер разбора: 'auto' (GigaChat AI с фолбэком на NLP), 'gigachat' (только AI), 'rules' (только локальный NLP)")


class ParsedFieldResponse(BaseModel):
    value: str | None = None
    confidence: float = Field(0.0, description="Уверенность разбора 0..1")
    evidence: list[str] = Field(default_factory=list, description="Фрагменты текста, из которых взято значение")


class SkillMentionResponse(BaseModel):
    name: str = Field(..., description="Название навыка из справочника")
    code: str = Field(..., description="Код навыка в справочнике")
    evidence: str = Field(..., description="Как навык написан в тексте")
    nice_to_have: bool = False


class NeedParseResponse(BaseModel):
    specialization: ParsedFieldResponse
    grade: ParsedFieldResponse
    work_format: ParsedFieldResponse
    city: ParsedFieldResponse
    skills: list[SkillMentionResponse] = Field(..., description="Обязательный стек")
    nice_to_have: list[SkillMentionResponse] = Field(..., description="«Будет плюсом»")
    salary_from: int | None = None
    salary_to: int | None = None
    salary_type: str | None = None
    is_gross: bool | None = None
    salary_evidence: str | None = None
    experience_years: int | None = None
    specialization_scores: dict[str, float] = Field(default_factory=dict)
    parser_source: str = Field("gigachat", description="Источник разбора: 'gigachat' (GigaChat AI) или 'rule_based' (внутренний NLP)")
    ai_available: bool = Field(True, description="Был ли доступен GigaChat AI при обработке")
    engine_badge: str = Field("GigaChat AI (152-ФЗ)", description="Отображаемый лейбл движка парсинга")


class ScoreComponents(BaseModel):
    C: float = Field(..., description="Category match (0.30 вес)")
    S: float = Field(..., description="Stack coverage (0.25 вес)")
    E: float = Field(..., description="Semantic similarity (0.10 вес)")
    T: float = Field(..., description="Test percentile (0.25 вес)")
    F: float = Field(..., description="FSP Score bonus (0.07 вес)")
    A: float = Field(..., description="Activity/recency (0.03 вес)")


class CandidateCardAnonymized(BaseModel):
    id: str
    full_name: str | None = None
    confirmed_category: str | None = None
    confirmed_specialization: str | None = None
    confirmed_grade: str | None = None
    is_grade_confirmed: bool = True
    grade_status: str = "CONFIRMED"
    grade_status_display: str = "Подтверждён"
    declared_grade: str | None = None
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


class RankedCandidateItem(BaseModel):
    candidate_id: str
    rank: int
    total_score: float
    score_percent: int
    components: ScoreComponents
    bullet_points: list[str] = Field(..., description="Объяснимые обоснования рекомендации (3-4 тезиса)")
    fsp_badge: str
    candidate_card: CandidateCardAnonymized


class RecommendationsResponse(BaseModel):
    need_id: str
    total_found: int
    snapshot_id: str | None = None
    items: list[RankedCandidateItem]


class SnapshotDetailResponse(BaseModel):
    id: str
    full_name: str | None = None
    need_id: str
    query_filters_hash: str | None = None
    created_at: str
    total_found: int
    items: list[Any] = Field(default_factory=list, description="Список кандидатов в сохраненном снимке")
    ranked_candidates: list[Any] = Field(default_factory=list, description="Кандидаты в сохраненном снимке")


class AIPitchRequest(BaseModel):
    need_id: str | None = None
    candidate_id: str
    score_percent: int = 85


class AIPitchResponse(BaseModel):
    candidate_id: str
    pitch: str
    provider: str = "gigachat"


class AIQuestionItem(BaseModel):
    topic: str
    question: str
    expected_answer: str


class AIQuestionsRequest(BaseModel):
    specialization: str
    grade: str
    skills: list[str] = Field(default_factory=list)
    count: int = 3


class AIQuestionsResponse(BaseModel):
    specialization: str
    grade: str
    questions: list[AIQuestionItem]
    provider: str = "gigachat"


class AICareerAdviceRequest(BaseModel):
    specialization: str | None = None
    grade: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience_years: float | None = None
    fsp_verified: bool = False
    percentile: int | None = None


class AICareerRoadmapStep(BaseModel):
    step: str
    timeframe: str | None = None
    action: str


class AICareerAdviceResponse(BaseModel):
    specialization: str
    grade: str
    overall_summary: str
    strengths: list[str]
    growth_points: list[str]
    recommended_fsp_discipline: str
    fsp_boost_tip: str
    career_roadmap: list[AICareerRoadmapStep] = Field(default_factory=list)
    provider: str = "gigachat"


class AIStatusResponse(BaseModel):
    provider: str
    is_configured: bool
    model: str
    scope: str
    status: str


def _salary_display(need: Need) -> str | None:
    if not (need.salary_budget_min or need.salary_budget_max):
        return None
    label = " (до вычета НДФЛ / Гросс)" if (need.is_gross or need.salary_type == "GROSS") else " (на руки / Нетто)"
    if need.salary_budget_min and need.salary_budget_max:
        return f"{need.salary_budget_min:,} – {need.salary_budget_max:,} ₽{label}".replace(",", " ")
    if need.salary_budget_max:
        return f"до {need.salary_budget_max:,} ₽{label}".replace(",", " ")
    return f"от {need.salary_budget_min:,} ₽{label}".replace(",", " ")


def _need_response(need: Need) -> NeedResponse:
    return NeedResponse(
        id=need.id,
        company_id=need.company_id,
        company_name=need.company.name if need.company else None,
        company_is_verified=bool(need.company and need.company.is_verified),
        title=need.title,
        target_specialization=need.target_specialization,
        target_grade=need.target_grade,
        required_skills=need.required_skills or [],
        raw_description=need.raw_description,
        salary_budget_min=need.salary_budget_min,
        salary_budget_max=need.salary_budget_max,
        salary_type=need.salary_type or "NET",
        is_gross=need.is_gross or False,
        salary_display=_salary_display(need),
        work_format=need.work_format,
        is_active=need.is_active,
        created_at=need.created_at.isoformat(),
    )


def _own_need(db: Session, need_id: str, company: Company) -> Need:
    """A need of the signed-in employer's company; another company's need is reported as missing."""
    need = db.query(Need).filter(Need.id == need_id).first()
    if not need or need.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NEED_NOT_FOUND", "message": f"Потребность {need_id} не найдена."},
        )
    return need


def _snapshot_response(s: SelectionSnapshot) -> SnapshotDetailResponse:
    payload = s.ranked_candidates_payload or []
    return SnapshotDetailResponse(
        id=s.id,
        need_id=s.need_id,
        query_filters_hash=s.query_filters_hash,
        created_at=s.created_at.isoformat() if s.created_at else "",
        total_found=len(payload),
        items=payload,
        ranked_candidates=payload,
    )


def _candidate_pool(db: Session):
    return db.query(CandidateProfile).options(
        joinedload(CandidateProfile.skills),
        joinedload(CandidateProfile.fsp_achievements),
        joinedload(CandidateProfile.user),
    )


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/needs/parse",
    response_model=NeedParseResponse,
    summary="Разобрать текст потребности или вакансии в структуру",
)
def parse_need_text(payload: NeedParseRequest):
    """Предлагает структуру потребности (специализация, грейд, стек, «будет плюсом», формат, город, зарплата)
    по свободному тексту.
    Использует гибридный пайплайн:
    1. Сначала пробует распознавание через отечественный GigaChat AI (152-ФЗ) со структурированным извлечением сущностей;
    2. При недоступности, таймауте или отсутствии ключей GigaChat — бесшовно откатывается на встроенный
       детерминированный NLP-парсер правил со словарём из 360+ IT-навыков."""
    return parse_need_hybrid(payload.text, payload.title, provider=payload.provider or "auto")


@router.get(
    "/needs",
    response_model=list[NeedResponse],
    summary="Получить список открытых вакансий (потребностей)",
)
def list_needs(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    company_id: str | None = Query(None, description="Фильтр по ID компании")
):
    """Возвращает активные вакансии с названием компании и зарплатной вилкой: кандидат видит условия до общения."""
    query = db.query(Need).options(joinedload(Need.company)).filter(Need.is_active.is_(True))
    if company_id:
        query = query.filter(Need.company_id == company_id)
    needs = query.order_by(Need.created_at.desc()).offset(offset).limit(limit).all()
    return [_need_response(need) for need in needs]


@router.post(
    "/needs",
    response_model=NeedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать потребность работодателя для формирования подборки",
)
def create_need(
    payload: NeedCreateRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Работодатель описывает потребность (стек, грейд, формат, бюджет) для двухэтапного подбора.
    Потребность создаётся от имени компании текущего работодателя."""
    if payload.company_id and payload.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN", "message": "Потребность можно создать только для своей компании."},
        )
    if payload.salary_budget_min and payload.salary_budget_max and payload.salary_budget_min > payload.salary_budget_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_SALARY_RANGE", "message": "Нижняя граница бюджета больше верхней."},
        )

    sal_type = (payload.salary_type or "NET").upper()
    is_gr = bool(payload.is_gross or (sal_type == "GROSS"))

    need = Need(
        company_id=company.id,
        title=payload.title,
        target_specialization=payload.target_specialization,
        target_grade=payload.target_grade,
        required_skills=payload.required_skills,
        raw_description=payload.raw_description,
        salary_budget_min=payload.salary_budget_min,
        salary_budget_max=payload.salary_budget_max,
        salary_type="GROSS" if is_gr else "NET",
        is_gross=is_gr,
        work_format=payload.work_format or "REMOTE",
        is_active=True,
    )
    db.add(need)
    db.commit()
    db.refresh(need)
    return _need_response(need)


@router.put(
    "/needs/{need_id}",
    response_model=NeedResponse,
    summary="Обновить потребность работодателя",
)
def update_need(
    need_id: str,
    payload: NeedUpdateRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Работодатель редактирует потребность своей компании."""
    need = _own_need(db, need_id, company)

    if payload.title is not None:
        need.title = payload.title
    if payload.target_specialization is not None:
        need.target_specialization = payload.target_specialization
    if payload.target_grade is not None:
        need.target_grade = payload.target_grade
    if payload.required_skills is not None:
        need.required_skills = payload.required_skills
    if payload.raw_description is not None:
        need.raw_description = payload.raw_description
    if payload.salary_budget_min is not None:
        need.salary_budget_min = payload.salary_budget_min
    if payload.salary_budget_max is not None:
        need.salary_budget_max = payload.salary_budget_max

    if payload.salary_type is not None or payload.is_gross is not None:
        new_type = payload.salary_type if payload.salary_type is not None else need.salary_type
        new_gross = payload.is_gross if payload.is_gross is not None else need.is_gross
        sal_type = (new_type or "NET").upper()
        is_gr = bool(new_gross or (sal_type == "GROSS"))
        need.salary_type = "GROSS" if is_gr else "NET"
        need.is_gross = is_gr

    if payload.work_format is not None:
        need.work_format = payload.work_format
    if payload.is_active is not None:
        need.is_active = payload.is_active

    db.commit()
    db.refresh(need)
    return _need_response(need)


@router.get(
    "/needs/{need_id}/recommendations",
    response_model=RecommendationsResponse,
    summary="Получить ранжированные и объяснимые рекомендации кандидатов по потребности",
)
def get_need_recommendations(
    need_id: str = Path(..., description="ID потребности работодателя"),
    limit: int = Query(50, ge=1, le=100),
    has_fsp: bool | None = Query(None, description="Фильтр: только с достижениями ФСП"),
    save_snapshot: bool = Query(True, description="Автоматически сохранить снимок выборки (Snapshot)"),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Выполняет двухэтапный подбор по потребности своей компании:

    1. Фильтрация пула (категория, смежный грейд, формат, город, зарплатный лимит).
    2. Скоринг по формуле: Score = 0.30*C + 0.25*S + 0.10*E + 0.25*T + 0.07*F + 0.03*A.
    3. Генерация 3-4 объяснимых тезисов на карточку.
    4. Фиксация состояния в SelectionSnapshot для возврата к поиску без потери данных.
    """
    need = _own_need(db, need_id, company)

    ranked_results = execute_two_stage_matching(
        all_candidates=_candidate_pool(db).all(),
        target_specialization=need.target_specialization,
        target_grade=need.target_grade,
        required_skills=need.required_skills or [],
        work_format=need.work_format,
        salary_budget_max=need.salary_budget_max,
        need_title=need.title,
        need_description=need.raw_description,
        top_limit=limit,
        has_fsp=has_fsp,
    )

    snapshot_id = None
    if save_snapshot and ranked_results:
        filters_dict = {
            "target_specialization": need.target_specialization,
            "target_grade": need.target_grade,
            "work_format": need.work_format,
            "salary_budget_max": need.salary_budget_max,
            "required_skills": need.required_skills,
        }
        if has_fsp is not None:
            filters_dict["has_fsp"] = has_fsp
        snap = SelectionSnapshotService.save_snapshot(
            db=db,
            need_id=need.id,
            filters=filters_dict,
            ranked_candidates=ranked_results,
        )
        snapshot_id = snap.id

    return RecommendationsResponse(
        need_id=need.id,
        total_found=len(ranked_results),
        snapshot_id=snapshot_id,
        items=ranked_results,
    )


@router.get(
    "/needs/{need_id}/snapshots",
    response_model=list[SnapshotDetailResponse],
    summary="Список сохраненных снимков работодателя",
)
def list_need_snapshots(
    need_id: str = Path(..., description="ID потребности работодателя"),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Список всех снимков подборок, сохраненных по потребности своей компании."""
    need = _own_need(db, need_id, company)
    return [_snapshot_response(s) for s in SelectionSnapshotService.list_snapshots(db, need.id)]


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=SnapshotDetailResponse,
    summary="Получение конкретного сохраненного снимка и списка кандидатов в нем",
)
def get_snapshot(
    snapshot_id: str = Path(..., description="ID сохраненного снимка"),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Возврат к сохраненному снимку без потери выборки и истории ранжирования."""
    snapshot = SelectionSnapshotService.get_snapshot_by_id(db, snapshot_id)
    if not snapshot or not snapshot.need or snapshot.need.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "SNAPSHOT_NOT_FOUND", "message": f"Снимок {snapshot_id} не найден."},
        )
    return _snapshot_response(snapshot)


@router.get(
    "/search/candidates",
    summary="Интерактивный фильтр и поиск кандидатов с объяснимым ранжированием",
    dependencies=[Depends(require_employer)],
)
def search_candidates(
    specialization: str | None = Query(None, description="Специализация (например, Backend, QA, Frontend)"),
    grade: str | None = Query(None, description="Подтверждённый грейд (JUNIOR, MIDDLE, SENIOR)"),
    skills: str | None = Query(None, description="Навыки через запятую, все обязательны (например: python, postgresql)"),
    work_format: str | None = Query(None, description="Формат работы (REMOTE, HYBRID, OFFICE)"),
    city: str | None = Query(None, description="Город"),
    salary_max: int | None = Query(None, description="Максимальная зарплата"),
    has_fsp: bool | None = Query(None, description="true — только с достижениями ФСП, false — только без них"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Поиск по всему банку кандидатов для работодателя: фильтры по специализации, грейду (категории), стеку,
    формату, городу, зарплате и достижениям ФСП, затем ранжирование по силе подтверждённого профиля."""
    skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else []

    query = _candidate_pool(db)
    if specialization:
        query = query.filter(func.upper(CandidateProfile.confirmed_specialization) == specialization.strip().upper())
    if grade:
        query = query.filter(func.upper(CandidateProfile.confirmed_grade) == grade.strip().upper())
    if work_format:
        query = query.filter(func.upper(CandidateProfile.work_format) == work_format.strip().upper())
    if city:
        query = query.filter(func.lower(CandidateProfile.city) == city.strip().lower())
    if salary_max is not None:
        query = query.filter(CandidateProfile.desired_salary_min <= salary_max)
    if has_fsp is True:
        query = query.filter((CandidateProfile.fsp_score > 0) | CandidateProfile.is_fsp_verified.is_(True))
    elif has_fsp is False:
        query = query.filter(
            (func.coalesce(CandidateProfile.fsp_score, 0) == 0) & CandidateProfile.is_fsp_verified.is_not(True)
        )

    ranked_results = execute_two_stage_matching(
        all_candidates=query.all(),
        target_specialization=specialization,
        target_grade=grade,
        required_skills=skills_list,
        work_format=work_format,
        city=city,
        salary_budget_max=salary_max,
        has_fsp=has_fsp,
        top_limit=limit,
        strict_filters=True,
    )

    return {
        "total_found": len(ranked_results),
        "items": ranked_results,
    }


@router.post(
    "/needs/{need_id}/apply",
    status_code=status.HTTP_200_OK,
    summary="Самостоятельный отклик кандидата на открытую вакансию (Дополнительный функционал, п. 2.1 ТЗ)",
)
def apply_to_need(
    need_id: str,
    candidate: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Кандидат откликается на вакансию сам. По ТЗ 2.2 работодатель сразу видит его контакты."""
    need = db.query(Need).filter(Need.id == need_id, Need.is_active.is_(True)).first()
    if not need:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NEED_NOT_FOUND", "message": f"Вакансия {need_id} не найдена или закрыта."},
        )

    existing = db.query(Invitation).filter(
        Invitation.need_id == need_id,
        Invitation.candidate_profile_id == candidate.id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "ALREADY_APPLIED", "message": "Вы уже откликнулись на эту вакансию (или получили приглашение)."},
        )

    invitation = Invitation(
        company_id=need.company_id,
        candidate_profile_id=candidate.id,
        need_id=need.id,
        status=InvitationStatus.APPLIED.value,
        salary_from=need.salary_budget_min or 0,
        salary_to=need.salary_budget_max or 0,
        salary_type=need.salary_type or "NET",
        is_gross=need.is_gross or False,
        message="Кандидат откликнулся на вашу вакансию.",
        contact_method="EMAIL",
    )
    db.add(invitation)
    db.commit()

    return {"success": True, "message": "Отклик отправлен. Работодатель видит ваш профиль и контакты."}


# ==========================================
# GIGACHAT / AI ASSISTANT ENDPOINTS (152-FZ)
# ==========================================

@router.get(
    "/ai/status",
    response_model=AIStatusResponse,
    summary="Статус подключения отечественной языковой модели (152-ФЗ)",
)
def get_ai_status():
    """Проверяет подключение к GigaChat / YandexGPT в соответствии с требованиями 152-ФЗ."""
    token = llm_client.get_access_token() if llm_client.is_configured else None
    return AIStatusResponse(
        provider=settings.LLM_PROVIDER,
        is_configured=llm_client.is_configured,
        model=settings.GIGACHAT_MODEL,
        scope=settings.GIGACHAT_SCOPE,
        status="ready" if token else ("configured_offline" if not llm_client.is_configured else "auth_error"),
    )


@router.post(
    "/needs/ai/pitch",
    response_model=AIPitchResponse,
    summary="Сгенерировать AI-питч кандидата для рекрутера через GigaChat",
)
def generate_ai_pitch(
    payload: AIPitchRequest,
    db: Session = Depends(get_db),
):
    """Генерирует аргументированный питч соискателя на базе GigaChat."""
    cand = db.query(CandidateProfile).filter(CandidateProfile.id == payload.candidate_id).first()
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANDIDATE_NOT_FOUND", "message": "Профиль соискателя не найден."},
        )

    need_title = "IT-специалист"
    need_spec = cand.confirmed_specialization or "BACKEND"
    need_grade = cand.confirmed_grade or "MIDDLE"

    if payload.need_id:
        need = db.query(Need).filter(Need.id == payload.need_id).first()
        if need:
            need_title = need.title
            need_spec = need.target_specialization
            need_grade = need.target_grade

    matched_skills = [cs.skill.name for cs in cand.skills if cs.skill]
    fsp_badge = "Участник соревнований ФСП" if cand.is_fsp_verified else None

    pitch = None
    if llm_client.is_configured:
        pitch = llm_client.generate_candidate_pitch(
            need_title=need_title,
            need_grade=need_grade,
            need_spec=need_spec,
            candidate_grade=cand.confirmed_grade or cand.declared_grade or "MIDDLE",
            matched_skills=matched_skills,
            fsp_badge=fsp_badge,
            score_percent=payload.score_percent,
        )

    if not pitch:
        # Fallback explanation if LLM is offline or unconfigured
        skills_str = ", ".join(matched_skills[:4]) if matched_skills else "профильному стеку"
        pitch = (
            f"Кандидат подтвердил квалификацию {cand.confirmed_grade or 'Middle'} в направлении {need_spec} "
            f"с совпадением по {skills_str}. "
            + ("Обладает спортивным разрядом и проверенными достижениями ФСП. " if cand.is_fsp_verified else "")
            + "Рекомендуется к техническому этапу собеседования."
        )

    return AIPitchResponse(
        candidate_id=cand.id,
        pitch=pitch,
        provider=settings.LLM_PROVIDER,
    )


@router.post(
    "/needs/ai/interview-questions",
    response_model=AIQuestionsResponse,
    summary="Сгенерировать вопросы к техническому собеседованию через GigaChat",
)
def generate_ai_interview_questions(payload: AIQuestionsRequest):
    """Генерирует вопросы для интервью соискателя под стек и грейд."""
    questions = None
    if llm_client.is_configured:
        questions = llm_client.generate_interview_questions(
            specialization=payload.specialization,
            grade=payload.grade,
            skills=payload.skills,
            count=payload.count,
        )

    if not questions:
        # Deterministic fallback
        questions = [
            {
                "topic": "Архитектура и проектирование",
                "question": f"Как вы проектируете масштабируемые сервисы для грейда {payload.grade} в {payload.specialization}?",
                "expected_answer": "Понимание принципов высокой доступности, шардирования БД и кеширования.",
            },
            {
                "topic": "Профильный стек технологий",
                "question": f"Опишите опыт работы со стеком: {', '.join(payload.skills[:3]) if payload.skills else 'ключевые библиотеки'}.",
                "expected_answer": "Практические кейсы оптимизации производительности и устранения узких мест.",
            },
        ]

    return AIQuestionsResponse(
        specialization=payload.specialization,
        grade=payload.grade,
        questions=[AIQuestionItem(**q) for q in questions],
        provider=settings.LLM_PROVIDER,
    )


@router.post(
    "/needs/ai/career-advice",
    response_model=AICareerAdviceResponse,
    summary="Сгенерировать персональные карьерные рекомендации и план роста от GigaChat",
)
def generate_ai_career_advice(payload: AICareerAdviceRequest):
    """Генерирует персональные рекомендации по развитию карьеры и выбору дисциплин ФСП."""
    spec = payload.specialization or "BACKEND"
    gr = payload.grade or "MIDDLE"

    advice = None
    if llm_client.is_configured:
        advice = llm_client.generate_career_advice(
            specialization=spec,
            grade=gr,
            skills=payload.skills,
            experience_years=payload.experience_years,
            fsp_verified=payload.fsp_verified,
            percentile=payload.percentile,
        )

    if not advice:
        # Deterministic domain fallback
        advice = {
            "overall_summary": f"Уверенный профиль уровня {gr} в направлении {spec}. Обладает сбалансированной теоретической подготовкой и высокой конкурентоспособностью в аккредитованных IT-компаниях.",
            "strengths": [
                f"Подтверждённая база по направлению {spec}",
                "Готовность к решению комплексных продуктовых и алгоритмических задач",
                "Высокий потенциал в инженерной оптимизации и надёжности сервисов",
            ],
            "growth_points": [
                "Глубокое изучение внутреннего устройства рантайма и профилирования памяти",
                "Проектирование отказоустойчивых распределённых систем и микросервисной архитектуры",
                "Внедрение практик автоматизированного нагрузочного тестирования и мониторинга",
            ],
            "recommended_fsp_discipline": "Программирование алгоритмическое",
            "fsp_boost_tip": "Участие в дисциплине «Программирование алгоритмическое» даёт максимальный повышающий коэффициент (+15% affinity boost) в формуле ранжирования работодателей.",
            "career_roadmap": [
                {
                    "step": "Этап 1: Углубление стека и архитектуры",
                    "timeframe": "1-2 месяца",
                    "action": f"Изучение углубленных тем для направления {spec} и паттернов проектирования.",
                },
                {
                    "step": "Этап 2: Соревнования ФСП",
                    "timeframe": "2-4 месяца",
                    "action": "Участие в турнирах по дисциплине «Программирование алгоритмическое» для роста в рейтинге ФСП.",
                },
                {
                    "step": "Этап 3: Подтверждение следующего грейда",
                    "timeframe": "4-6 месяцев",
                    "action": "Прохождение квалификационного IRT-теста ФСП с повышением процентиля.",
                },
            ],
        }

    roadmap_raw = advice.get("career_roadmap") or []
    roadmap = []
    if isinstance(roadmap_raw, list):
        for item in roadmap_raw:
            if isinstance(item, dict):
                roadmap.append(
                    AICareerRoadmapStep(
                        step=str(item.get("step", "")),
                        timeframe=item.get("timeframe"),
                        action=str(item.get("action", "")),
                    )
                )

    return AICareerAdviceResponse(
        specialization=spec,
        grade=gr,
        overall_summary=str(advice.get("overall_summary", "")),
        strengths=list(advice.get("strengths", [])),
        growth_points=list(advice.get("growth_points", [])),
        recommended_fsp_discipline=str(advice.get("recommended_fsp_discipline", "Программирование алгоритмическое")),
        fsp_boost_tip=str(advice.get("fsp_boost_tip", "")),
        career_roadmap=roadmap,
        provider=settings.LLM_PROVIDER,
    )
