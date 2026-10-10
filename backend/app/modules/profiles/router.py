"""Profiles and Standardization API router.

Provides:
- Candidate profile view and update (/me/profile): the signed-in candidate's own profile only
- Company profile view and update (/companies/me): the signed-in employer's own company only
- Standardized candidate PDF exports with QR code (/candidates/{id}/pdf, /me/pdf)
- Public verification of a candidate's category (/verify/candidates/{id}), the target of the PDF QR code
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

try:
    from backend.app.core.database import get_db
    from backend.app.models.candidate import CandidateProfile, CandidateSkill, CandidateSpecialization
    from backend.app.models.company import Company
    from backend.app.models.dictionary import Skill, SkillSynonym
    from backend.app.models.user import User
    from backend.app.modules.auth.service import get_current_candidate, get_current_company, get_current_user
    from backend.app.modules.profiles.pdf_service import generate_candidate_pdf, generate_candidate_qr_png
    from backend.app.modules.profiles.schemas import (
        CandidateFSPAchievementInfo,
        CandidateProfileResponse,
        CandidateProfileUpdateRequest,
        CandidateSkillInfo,
        CandidateVerificationResponse,
        CompanyResponse,
        CompanyUpdateRequest,
    )
except ImportError:
    from app.core.database import get_db
    from app.models.candidate import CandidateProfile, CandidateSkill, CandidateSpecialization
    from app.models.company import Company
    from app.models.dictionary import Skill, SkillSynonym
    from app.models.user import User
    from app.modules.auth.service import get_current_candidate, get_current_company, get_current_user
    from app.modules.profiles.pdf_service import generate_candidate_pdf, generate_candidate_qr_png
    from app.modules.profiles.schemas import (
        CandidateFSPAchievementInfo,
        CandidateProfileResponse,
        CandidateProfileUpdateRequest,
        CandidateSkillInfo,
        CandidateVerificationResponse,
        CompanyResponse,
        CompanyUpdateRequest,
    )

router = APIRouter(tags=["Profiles & Standardization"])

PROFILE_STATUSES = {"ACTIVELY_SEARCHING", "OPEN", "HIDDEN"}
WORK_FORMATS = {"REMOTE", "HYBRID", "OFFICE"}
# Skills the candidate typed or took from the resume; test and FSP confirmations are never touched by the form
DECLARED_SKILL_SOURCES = {"CLAIMED", "RESUME"}
MAX_DECLARED_SKILLS = 30


def _load_candidate(db: Session, candidate_id: str) -> CandidateProfile | None:
    return (
        db.query(CandidateProfile)
        .options(
            joinedload(CandidateProfile.skills).joinedload(CandidateSkill.skill),
            joinedload(CandidateProfile.fsp_achievements),
            joinedload(CandidateProfile.user),
        )
        .filter(CandidateProfile.id == candidate_id)
        .first()
    )


def _is_unconfirmed(cand: CandidateProfile) -> bool:
    return not cand.confirmed_grade or cand.confirmed_grade.strip().upper() in (
        "UNCONFIRMED",
        "НЕ_ПОДТВЕРЖДЕН",
        "НЕ ПОДТВЕРЖДЕН",
        "НЕ ПОДТВЕРЖДЁН",
        "НЕ_ПОДТВЕРЖДЁН",
        "NONE",
    )


def _serialize_candidate_profile(cand: CandidateProfile) -> CandidateProfileResponse:
    skills_list = []
    for cs in (cand.skills or []):
        skills_list.append(
            CandidateSkillInfo(
                id=cs.id,
                skill_id=cs.skill_id,
                name=(cs.skill.name if cs.skill else cs.skill_id),
                code=(cs.skill.code if cs.skill else cs.skill_id),
                confirmation_source=cs.confirmation_source,
                weight=cs.weight or 1.0,
            )
        )

    ach_list = []
    for a in (cand.fsp_achievements or []):
        ach_list.append(
            CandidateFSPAchievementInfo(
                id=a.id,
                event_name=a.event_name,
                discipline=a.discipline,
                level=a.level,
                result=a.result,
                sport_category=a.sport_category,
                event_date=a.event_date.isoformat() if a.event_date else None,
            )
        )

    sal_type = getattr(cand, "salary_type", "NET") or "NET"
    is_gr = getattr(cand, "is_gross", False) or (sal_type == "GROSS")
    sal_disp = None
    if cand.desired_salary_min:
        label = " (до вычета НДФЛ / Гросс)" if is_gr else " (на руки / Нетто)"
        sal_disp = f"{cand.desired_salary_min:,} ₽{label}".replace(",", " ")

    is_unconfirmed = _is_unconfirmed(cand)

    return CandidateProfileResponse(
        id=cand.id,
        user_id=cand.user_id,
        first_name=cand.first_name,
        last_name=cand.last_name,
        email=cand.user.email if cand.user else None,
        phone=cand.phone,
        telegram=cand.telegram,
        city=cand.city,
        work_format=cand.work_format,
        desired_salary_min=cand.desired_salary_min,
        salary_type=sal_type,
        is_gross=is_gr,
        salary_display=sal_disp,
        status=cand.status or "ACTIVELY_SEARCHING",
        confirmed_category=cand.confirmed_category,
        confirmed_specialization=cand.confirmed_specialization,
        confirmed_grade=cand.confirmed_grade,
        is_grade_confirmed=not is_unconfirmed,
        grade_status="UNCONFIRMED" if is_unconfirmed else "CONFIRMED",
        grade_status_display="Не подтверждён" if is_unconfirmed else "Подтверждён",
        declared_grade=getattr(cand, "declared_grade", None),
        category_percentile=cand.category_percentile,
        last_theta=cand.last_theta or 0.0,
        last_se=cand.last_se or 1.0,
        fsp_id=cand.fsp_id,
        fsp_score=cand.fsp_score or 0.0,
        is_fsp_verified=cand.is_fsp_verified or False,
        hide_contacts_globally=cand.hide_contacts_globally,
        skills=skills_list,
        fsp_achievements=ach_list,
        experience_years=cand.experience_years,
        stack=cand.stack,
        soft_skills=cand.soft_skills,
        roles=cand.roles,
        about_me=cand.about_me,
        created_at=cand.created_at.isoformat() if cand.created_at else "",
        updated_at=cand.updated_at.isoformat() if cand.updated_at else "",
    )


def _serialize_company(comp: Company) -> CompanyResponse:
    return CompanyResponse(
        id=comp.id,
        name=comp.name,
        inn=comp.inn,
        website=comp.website,
        description=comp.description,
        logo_url=comp.logo_url,
        is_verified=comp.is_verified,
        direction=comp.direction,
        contacts=comp.contacts,
        created_at=comp.created_at.isoformat() if comp.created_at else "",
    )


def split_stack(stack: str | None) -> list[str]:
    """Skill names from the free-text stack field, in order, without case-insensitive duplicates."""
    names: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;\n]", stack or ""):
        name = part.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names[:MAX_DECLARED_SKILLS]


def sync_declared_skills(db: Session, cand: CandidateProfile, stack: str | None) -> None:
    """Mirror the declared stack into the candidate's skills so that matching can count them.

    Declared skills get the CLAIMED source (weight 0.3 in the S component of the ranking); skills confirmed by
    the test or by FSP keep their source. Names that are not in the skills dictionary stay only in the free text.
    """
    by_name: dict[str, Skill] = {}
    for skill in db.query(Skill).all():
        by_name.setdefault(skill.name.strip().lower(), skill)
        by_name.setdefault(skill.code.strip().lower(), skill)
    for syn in db.query(SkillSynonym).all():
        if syn.skill is not None:
            by_name.setdefault(syn.synonym.strip().lower(), syn.skill)

    wanted: dict[str, Skill] = {}
    for name in split_stack(stack):
        skill = by_name.get(name.lower())
        if skill is not None:
            wanted.setdefault(skill.id, skill)

    held = {cs.skill_id: cs for cs in cand.skills}
    for skill_id, cs in held.items():
        if (cs.confirmation_source or "CLAIMED").upper() in DECLARED_SKILL_SOURCES and skill_id not in wanted:
            cand.skills.remove(cs)
    for skill_id, skill in wanted.items():
        if skill_id not in held:
            cand.skills.append(CandidateSkill(skill_id=skill.id, skill=skill, confirmation_source="CLAIMED", weight=0.3))


# ==========================================
# CANDIDATE PROFILE ENDPOINTS
# ==========================================

@router.get(
    "/me/profile",
    response_model=CandidateProfileResponse,
    summary="Возвращает данные профиля текущего кандидата",
)
@router.get(
    "/profiles/me",
    response_model=CandidateProfileResponse,
    include_in_schema=False,
)
def get_my_profile(
    me: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Полная анкета текущего кандидата с навыками и статусом ФСП. Доступна только самому кандидату."""
    return _serialize_candidate_profile(_load_candidate(db, me.id))


@router.put(
    "/me/profile",
    response_model=CandidateProfileResponse,
    summary="Обновление профиля кандидата (контакты, город, формат, зарплата, анкета)",
)
def update_my_profile(
    payload: CandidateProfileUpdateRequest,
    me: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Обновляет контакты, город, формат работы, зарплатные ожидания и анкету кандидата (стаж, стек, роли,
    soft-skills, «о себе»). Стек из анкеты попадает в навыки профиля с источником «заявлено кандидатом»."""
    cand = _load_candidate(db, me.id)

    if payload.status is not None and payload.status.upper() not in PROFILE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Недопустимый статус поиска. Допустимо: {', '.join(sorted(PROFILE_STATUSES))}.",
        )
    if payload.work_format is not None and payload.work_format.upper() not in WORK_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Недопустимый формат работы. Допустимо: {', '.join(sorted(WORK_FORMATS))}.",
        )

    if payload.first_name is not None:
        cand.first_name = payload.first_name
    if payload.last_name is not None:
        cand.last_name = payload.last_name
    if payload.phone is not None:
        cand.phone = payload.phone
    if payload.telegram is not None:
        cand.telegram = payload.telegram
    if payload.city is not None:
        cand.city = payload.city
    if payload.work_format is not None:
        cand.work_format = payload.work_format.upper()
    if payload.desired_salary_min is not None:
        cand.desired_salary_min = payload.desired_salary_min
    if payload.salary_type is not None:
        cand.salary_type = payload.salary_type.upper()
        cand.is_gross = (payload.salary_type.upper() == "GROSS")
    if payload.is_gross is not None:
        cand.is_gross = payload.is_gross
        cand.salary_type = "GROSS" if payload.is_gross else "NET"
    if payload.status is not None:
        cand.status = payload.status.upper()
    if payload.experience_years is not None:
        cand.experience_years = payload.experience_years
    if payload.stack is not None:
        cand.stack = ", ".join(split_stack(payload.stack)) or None
        sync_declared_skills(db, cand, payload.stack)
    if payload.soft_skills is not None:
        cand.soft_skills = payload.soft_skills or None
    if payload.roles is not None:
        cand.roles = payload.roles or None
    if payload.about_me is not None:
        cand.about_me = payload.about_me or None

    db.commit()
    return _serialize_candidate_profile(_load_candidate(db, cand.id))


# ==========================================
# COMPANY PROFILE ENDPOINTS
# ==========================================

@router.get(
    "/companies/me",
    response_model=CompanyResponse,
    summary="Данные профиля компании текущего работодателя",
)
def get_company_profile(company: Company = Depends(get_current_company)):
    """Возвращает карточку компании работодателя."""
    return _serialize_company(company)


@router.put(
    "/companies/me",
    response_model=CompanyResponse,
    summary="Обновление карточки компании",
)
def update_company_profile(
    payload: CompanyUpdateRequest,
    comp: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Обновляет реквизиты, описание, сайт и логотип компании текущего работодателя."""
    if payload.name is not None:
        comp.name = payload.name
    if payload.inn is not None and payload.inn != comp.inn:
        comp.inn = payload.inn
        comp.is_verified = False  # a changed INN has to be checked again
    if payload.website is not None:
        comp.website = payload.website
    if payload.description is not None:
        comp.description = payload.description
    if payload.logo_url is not None:
        comp.logo_url = payload.logo_url
    if payload.direction is not None:
        comp.direction = payload.direction
    if payload.contacts is not None:
        comp.contacts = payload.contacts

    db.commit()
    db.refresh(comp)
    return _serialize_company(comp)


# ==========================================
# PDF EXPORT AND VERIFICATION ENDPOINTS
# ==========================================

def _pdf_response(cand: CandidateProfile, request: Request | None = None) -> Response:
    base_url = None
    if request:
        f_host = request.headers.get("x-forwarded-host")
        f_proto = request.headers.get("x-forwarded-proto", "http")
        if f_host:
            base_url = f"{f_proto}://{f_host}"
        else:
            host = request.headers.get("host")
            if host and not any(h in host for h in ("localhost", "127.0.0.1", "backend", "testserver")):
                base_url = f"http://{host}"
    pdf_bytes = generate_candidate_pdf(cand, base_url=base_url)
    filename = f"fsp_candidate_{cand.id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/candidates/{id}/pdf",
    summary="Выгрузка стандартизированного PDF профиля кандидата с QR-кодом",
    response_class=Response,
)
def get_candidate_pdf(
    id: str = Path(..., description="ID кандидата"),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """PDF-профиль кандидата без контактов. Доступен самому кандидату и работодателям;
    профиль, скрытый кандидатом, работодатель не получает."""
    cand = _load_candidate(db, id)
    is_owner = cand is not None and cand.user_id == current_user.id
    if not cand or (not is_owner and (current_user.role == "CANDIDATE" or cand.status == "HIDDEN")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANDIDATE_NOT_FOUND", "message": f"Кандидат с ID {id} не найден."},
        )
    return _pdf_response(cand, request=request)


@router.get(
    "/me/pdf",
    summary="Выгрузка своего стандартизированного PDF профиля с QR-кодом",
    response_class=Response,
)
def get_my_pdf(
    request: Request = None,
    me: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Выгружает собственный стандартизированный PDF-профиль текущего кандидата."""
    return _pdf_response(_load_candidate(db, me.id), request=request)


@router.get(
    "/verify/candidates/{id}",
    response_model=CandidateVerificationResponse,
    summary="Публичная проверка категории кандидата по QR-коду из PDF-профиля",
)
def verify_candidate(
    id: str = Path(..., description="ID кандидата из PDF-профиля"),
    db: Session = Depends(get_db),
):
    """Сверка PDF-профиля с данными платформы: категория, статус грейда и привязка ФСП на текущий момент.
    Контакты не возвращаются; профиль, скрытый кандидатом, не показывается."""
    cand = _load_candidate(db, id)
    if not cand or cand.status == "HIDDEN":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANDIDATE_NOT_FOUND", "message": "Профиль не найден или скрыт кандидатом."},
        )
    unconfirmed = _is_unconfirmed(cand)
    initial = f" {cand.last_name[0]}." if cand.last_name else ""

    confirmed_skills = [
        cs.skill.name if cs.skill else cs.skill_id
        for cs in (cand.skills or [])
        if cs.confirmation_source in ("ASSESSMENT", "FSP")
    ]
    fsp_disciplines = list(dict.fromkeys(a.discipline for a in (cand.fsp_achievements or []) if a.discipline))

    import hashlib
    hash_payload = f"{cand.id}:{cand.confirmed_category or 'NONE'}:{cand.is_fsp_verified}"
    v_hash = hashlib.sha256(hash_payload.encode()).hexdigest()[:16].upper()

    return CandidateVerificationResponse(
        candidate_id=cand.id,
        name=f"{cand.first_name or 'Кандидат'}{initial}",
        confirmed_category=None if unconfirmed else cand.confirmed_category,
        grade_status="UNCONFIRMED" if unconfirmed else "CONFIRMED",
        is_fsp_verified=bool(cand.is_fsp_verified),
        category_percentile=cand.category_percentile if not unconfirmed else None,
        confirmed_specialization=cand.confirmed_specialization,
        confirmed_grade=None if unconfirmed else cand.confirmed_grade,
        declared_grade=cand.declared_grade,
        city=cand.city,
        work_format=cand.work_format,
        experience_years=cand.experience_years,
        confirmed_skills=confirmed_skills,
        fsp_achievements_count=len(cand.fsp_achievements or []),
        fsp_disciplines=fsp_disciplines,
        verification_hash=v_hash,
        checked_at=datetime.now(timezone.utc),
    )


@router.get(
    "/verify/candidates/{id}/pdf",
    summary="Публичное скачивание стандартизированного PDF сертификата с QR-кодом (без контактов, 152-ФЗ)",
    response_class=Response,
)
def get_verified_candidate_pdf(
    id: str = Path(..., description="ID кандидата"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Публичный стандартизированный PDF-профиль без контактов (152-ФЗ).
    Позволяет любому посетителю публичной страницы сертификата выгрузить PDF-паспорт."""
    cand = _load_candidate(db, id)
    if not cand or cand.status == "HIDDEN":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANDIDATE_NOT_FOUND", "message": "Профиль не найден или скрыт кандидатом."},
        )
    return _pdf_response(cand, request=request)


@router.get(
    "/verify/candidates/{id}/qr",
    summary="Публичное получение PNG изображения QR-кода верификации",
    response_class=Response,
)
def get_verified_candidate_qr(
    id: str = Path(..., description="ID кандидата"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Возвращает PNG-изображение QR-кода, ведущего на страницу верификации кандидата."""
    cand = _load_candidate(db, id)
    if not cand or cand.status == "HIDDEN":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANDIDATE_NOT_FOUND", "message": "Профиль не найден или скрыт кандидатом."},
        )
    base_url = None
    if request:
        f_host = request.headers.get("x-forwarded-host")
        f_proto = request.headers.get("x-forwarded-proto", "http")
        if f_host:
            base_url = f"{f_proto}://{f_host}"
        else:
            host = request.headers.get("host")
            if host and not any(h in host for h in ("localhost", "127.0.0.1", "backend", "testserver")):
                base_url = f"http://{host}"
    png_bytes = generate_candidate_qr_png(cand.id, base_url=base_url)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ==========================================
# ADDITIONAL (DECLARED) SPECIALIZATIONS
# ==========================================

class SpecializationAddRequest(BaseModel):
    specialization: str
    grade: str


class CandidateSpecializationResponse(BaseModel):
    id: str
    specialization: str
    grade: str
    is_confirmed: bool = False


@router.post(
    "/me/specializations",
    response_model=CandidateSpecializationResponse,
    summary="Добавление заявленной дополнительной специализации",
)
def add_specialization(
    payload: SpecializationAddRequest,
    me: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Кандидат указывает дополнительное направление и желаемый грейд. Это заявление, а не категория:
    категорию и грейд присваивает только тест, поэтому в подборе участвует подтверждённая категория."""
    spec = CandidateSpecialization(
        candidate_profile_id=me.id,
        specialization=payload.specialization.strip().upper().replace(" ", "_"),
        grade=payload.grade.strip().upper(),
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)
    return CandidateSpecializationResponse(id=spec.id, specialization=spec.specialization, grade=spec.grade)


@router.get(
    "/me/specializations",
    response_model=list[CandidateSpecializationResponse],
    summary="Заявленные дополнительные специализации кандидата",
)
def get_specializations(
    me: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Дополнительные специализации текущего кандидата (заявленные, без подтверждения тестом)."""
    specs = db.query(CandidateSpecialization).filter(CandidateSpecialization.candidate_profile_id == me.id).all()
    return [CandidateSpecializationResponse(id=s.id, specialization=s.specialization, grade=s.grade) for s in specs]
