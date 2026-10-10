"""FSP endpoints for linking athlete profile and achievements."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

try:
    from backend.app.core.database import get_db
    from backend.app.models.candidate import CandidateProfile, FSPAchievement
    from backend.app.models.user import Consent
    from backend.app.modules.auth.service import get_current_candidate
    from backend.app.modules.fsp.adapter import fsp_client
    from backend.app.modules.fsp.score import (
        calculate_fsp_score,
        format_fsp_ranking_bullet,
    )
except ImportError:
    from app.core.database import get_db
    from app.models.candidate import CandidateProfile, FSPAchievement
    from app.models.user import Consent
    from app.modules.auth.service import get_current_candidate
    from app.modules.fsp.adapter import fsp_client
    from app.modules.fsp.score import calculate_fsp_score, format_fsp_ranking_bullet

router = APIRouter(prefix="/me/fsp", tags=["FSP Federation"])


class FSPLinkRequest(BaseModel):
    fsp_id: str = Field(..., description="Идентификатор участника в реестре ФСП (например, FSP-1001)")
    consent_given: bool = Field(
        ...,
        description="Согласие субъекта ПДн на интеграцию и верификацию спортивных достижений (152-ФЗ)",
    )


class FSPAchievementResponse(BaseModel):
    id: str
    event_name: str
    event_date: str | None = None
    discipline: str
    level: str
    result: str
    sport_category: str | None = None
    calculated_weight: float


class FSPLinkResponse(BaseModel):
    fsp_id: str
    is_fsp_verified: bool
    fsp_score: float
    badge: str
    description: str
    sport_rank: str | None = None
    achievements: list[FSPAchievementResponse]
    explanation_bullet: str


@router.post(
    "/link",
    response_model=FSPLinkResponse,
    summary="Привязать профиль спортсмена ФСП и верифицировать достижения",
)
async def link_fsp_profile(
    req: FSPLinkRequest,
    profile: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Привязка FSP ID к анкете кандидата с получением достижений из внешнего реестра.

    Требования:
    - Обязательное явное согласие пользователя (152-ФЗ)
    - Валидация наличия спортсмена в реестре ФСП
    - Расчёт FSP Score с весами и временем затухания
    - Сохранение достижений в профиль кандидата
    - Один FSP ID привязывается только к одному профилю
    """
    if not req.consent_given:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "FSP_CONSENT_REQUIRED_152_FZ",
                "message": "Для привязки достижений необходимо дать согласие на обработку персональных данных и запрос сведений из реестра ФСП.",
            },
        )

    fsp_id = req.fsp_id.strip()
    taken = (
        db.query(CandidateProfile.id)
        .filter(CandidateProfile.fsp_id == fsp_id, CandidateProfile.is_fsp_verified.is_(True),
                CandidateProfile.id != profile.id)
        .first()
    )
    if taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "FSP_ID_ALREADY_LINKED",
                "message": "Этот FSP ID уже привязан к другому профилю. Если это ваш ID, обратитесь в поддержку.",
            },
        )

    # Fetch from FSP registry adapter
    registry_data = await fsp_client.get_participant_achievements(fsp_id)
    if not registry_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "FSP_PARTICIPANT_NOT_FOUND",
                "message": f"Участник с кодом {req.fsp_id} не найден в официальном реестре соревнований ФСП.",
            },
        )

    achievements_list = registry_data.get("achievements", [])
    sport_rank = registry_data.get("current_sport_rank")

    # Compute score
    score_data = calculate_fsp_score(achievements_list, sport_rank)

    # Save to database
    profile.fsp_id = fsp_id
    profile.is_fsp_verified = True
    profile.fsp_score = score_data["normalized_score"]

    # Record consent in consents table if user exists
    if profile.user_id:
        existing_consent = (
            db.query(Consent)
            .filter(
                Consent.user_id == profile.user_id,
                Consent.consent_type == "FSP_DATA_EXCHANGE",
            )
            .first()
        )
        if not existing_consent:
            consent_record = Consent(
                user_id=profile.user_id,
                consent_type="FSP_DATA_EXCHANGE",
                version="1.0",
                is_given=True,
                given_at=datetime.now(timezone.utc),
            )
            db.add(consent_record)

    # Replace / update achievements
    db.query(FSPAchievement).filter(FSPAchievement.candidate_profile_id == profile.id).delete()

    created_achievements: list[FSPAchievement] = []
    for ach in achievements_list:
        ev_date = ach.get("event_date")
        parsed_date = None
        if isinstance(ev_date, str):
            try:
                parsed_date = datetime.fromisoformat(ev_date.replace("Z", "+00:00"))
            except ValueError:
                parsed_date = None

        db_ach = FSPAchievement(
            candidate_profile_id=profile.id,
            event_name=ach.get("event_name", "Соревнование ФСП"),
            event_date=parsed_date,
            discipline=ach.get("discipline", "Спортивное программирование"),
            level=ach.get("level", "ALL_RUSSIAN"),
            result=ach.get("result", "PARTICIPANT"),
            sport_category=ach.get("sport_category"),
            calculated_weight=float(ach.get("calculated_weight", 0.0)),
        )
        db.add(db_ach)
        created_achievements.append(db_ach)

    db.commit()
    db.refresh(profile)

    explanation = format_fsp_ranking_bullet(
        fsp_score=profile.fsp_score,
        achievements=achievements_list,
        sport_rank=sport_rank,
    )

    response_achievements = [
        FSPAchievementResponse(
            id=a.id,
            event_name=a.event_name,
            event_date=a.event_date.isoformat() if a.event_date else None,
            discipline=a.discipline,
            level=a.level,
            result=a.result,
            sport_category=a.sport_category,
            calculated_weight=a.calculated_weight,
        )
        for a in created_achievements
    ]

    return FSPLinkResponse(
        fsp_id=profile.fsp_id,
        is_fsp_verified=profile.is_fsp_verified,
        fsp_score=profile.fsp_score,
        badge=score_data["badge"],
        description=score_data["description"],
        sport_rank=sport_rank,
        achievements=response_achievements,
        explanation_bullet=explanation,
    )


@router.get(
    "/status",
    summary="Получить текущий статус достижений ФСП для текущего кандидата",
)
def get_fsp_status(
    profile: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
):
    """Возвращает информацию о текущем FSP Score или нейтральный статус при отсутствии."""
    achievements = db.query(FSPAchievement).filter(FSPAchievement.candidate_profile_id == profile.id).all()

    ach_dicts = [
        {
            "event_name": a.event_name,
            "event_date": a.event_date,
            "discipline": a.discipline,
            "level": a.level,
            "result": a.result,
            "sport_category": a.sport_category,
        }
        for a in achievements
    ]
    sport_rank = next((a.sport_category for a in achievements if a.sport_category), None)
    score_data = calculate_fsp_score(ach_dicts, sport_rank)

    explanation = format_fsp_ranking_bullet(
        fsp_score=profile.fsp_score,
        achievements=ach_dicts,
        sport_rank=sport_rank,
    )

    return {
        "candidate_profile_id": profile.id,
        "fsp_id": profile.fsp_id,
        "is_fsp_verified": profile.is_fsp_verified,
        "fsp_score": profile.fsp_score,
        "badge": score_data["badge"],
        "description": score_data["description"],
        "has_history": score_data["has_history"],
        "achievements_count": len(achievements),
        "explanation_bullet": explanation,
    }
