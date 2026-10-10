"""Mock FSP (Федерация спортивного программирования) Registry Microservice.

Simulates the external official sports programming registry API:
- Participant lookup by FSP ID
- Verified competition history (ЛЦТ, Чемпионат России, Кубок России, региональные турниры)
- Official results (Победитель, Призёр, Финалист, Участник)
- Disciplines (Продуктовое программирование, Алгоритмическое программирование)
- Sports categories / ranks (КМС, 1 разряд, Мастер спорта)
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="FSP Registry Mock Service",
    description="Реестр участников и спортивных достижений Федерации спортивного программирования",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FSPAchievementItem(BaseModel):
    id: str = Field(..., description="Уникальный идентификатор записи в реестре")
    event_name: str = Field(..., description="Название соревнования")
    event_date: str = Field(..., description="Дата проведения (ISO 8601)")
    discipline: str = Field(..., description="Дисциплина спортивного программирования")
    level: str = Field(..., description="Уровень (INTERNATIONAL, ALL_RUSSIAN, INTERREGIONAL, REGIONAL)")
    result: str = Field(..., description="Результат (WINNER, PRIZE_WINNER, FINALIST, PARTICIPANT)")
    sport_category: str | None = Field(None, description="Присвоенный спортивный разряд или звание")
    certificate_id: str | None = Field(None, description="Номер официального протокола или сертификата")


class FSPParticipantProfile(BaseModel):
    fsp_id: str = Field(..., description="Единый идентификатор спортсмена ФСП")
    full_name: str = Field(..., description="ФИО спортсмена")
    region: str = Field(..., description="Субъект РФ / Региональное отделение")
    current_sport_rank: str | None = Field(None, description="Текущий спортивный разряд/звание")
    status: str = Field("ACTIVE", description="Статус в реестре (ACTIVE, INACTIVE)")
    achievements: list[FSPAchievementItem] = Field(default_factory=list, description="Список официальных достижений")


# Pre-configured realistic datasets for testing and demonstrations
MOCK_PARTICIPANTS: dict[str, dict[str, Any]] = {
    "FSP-1001": {
        "fsp_id": "FSP-1001",
        "full_name": "Иванов Алексей Сергеевич",
        "region": "Москва",
        "current_sport_rank": "КМС",
        "status": "ACTIVE",
        "achievements": [
            {
                "id": "ach-1001-1",
                "event_name": "Чемпионат России по спортивному программированию 2025",
                "event_date": "2025-11-20T10:00:00Z",
                "discipline": "Продуктовое программирование",
                "level": "ALL_RUSSIAN",
                "result": "WINNER",
                "sport_category": "КМС",
                "certificate_id": "FSP-RU-2025-0142",
            },
            {
                "id": "ach-1001-2",
                "event_name": "Хакатон «Лидеры цифровой трансформации» (ЛЦТ) 2025",
                "event_date": "2025-06-15T12:00:00Z",
                "discipline": "Продуктовое программирование",
                "level": "ALL_RUSSIAN",
                "result": "PRIZE_WINNER",
                "sport_category": "1 разряд",
                "certificate_id": "LCT-2025-9981",
            },
            {
                "id": "ach-1001-3",
                "event_name": "Чемпионат Москвы по спортивному программированию 2024",
                "event_date": "2024-04-12T09:00:00Z",
                "discipline": "Алгоритмическое программирование",
                "level": "REGIONAL",
                "result": "WINNER",
                "sport_category": "1 разряд",
                "certificate_id": "FSP-MSK-2024-0311",
            },
        ],
    },
    "FSP-1002": {
        "fsp_id": "FSP-1002",
        "full_name": "Смирнова Екатерина Дмитриевна",
        "region": "Санкт-Петербург",
        "current_sport_rank": "Мастер спорта",
        "status": "ACTIVE",
        "achievements": [
            {
                "id": "ach-1002-1",
                "event_name": "Кубок России по спортивному программированию 2025",
                "event_date": "2025-09-18T10:00:00Z",
                "discipline": "Алгоритмическое программирование",
                "level": "ALL_RUSSIAN",
                "result": "WINNER",
                "sport_category": "Мастер спорта",
                "certificate_id": "FSP-CUP-2025-0012",
            },
            {
                "id": "ach-1002-2",
                "event_name": "Чемпионат России по спортивному программированию 2024",
                "event_date": "2024-11-10T11:00:00Z",
                "discipline": "Алгоритмическое программирование",
                "level": "ALL_RUSSIAN",
                "result": "PRIZE_WINNER",
                "sport_category": "КМС",
                "certificate_id": "FSP-RU-2024-0087",
            },
        ],
    },
    "FSP-1003": {
        "fsp_id": "FSP-1003",
        "full_name": "Козлов Михаил Андреевич",
        "region": "Татарстан",
        "current_sport_rank": "1 разряд",
        "status": "ACTIVE",
        "achievements": [
            {
                "id": "ach-1003-1",
                "event_name": "Хакатон «Лидеры цифровой трансформации» (ЛЦТ) 2025",
                "event_date": "2025-06-15T12:00:00Z",
                "discipline": "Продуктовое программирование",
                "level": "ALL_RUSSIAN",
                "result": "FINALIST",
                "sport_category": "1 разряд",
                "certificate_id": "LCT-2025-1102",
            },
            {
                "id": "ach-1003-2",
                "event_name": "Региональный чемпионат Республики Татарстан 2024",
                "event_date": "2024-05-20T10:00:00Z",
                "discipline": "Продуктовое программирование",
                "level": "REGIONAL",
                "result": "PRIZE_WINNER",
                "sport_category": "2 разряд",
                "certificate_id": "FSP-RT-2024-0044",
            },
        ],
    },
    "FSP-2024": {
        "fsp_id": "FSP-2024",
        "full_name": "Новиков Артем Павлович",
        "region": "Новосибирская область",
        "current_sport_rank": "2 разряд",
        "status": "ACTIVE",
        "achievements": [
            {
                "id": "ach-2024-1",
                "event_name": "Кубок Сибири по спортивному программированию 2025",
                "event_date": "2025-03-22T08:00:00Z",
                "discipline": "Алгоритмическое программирование",
                "level": "INTERREGIONAL",
                "result": "FINALIST",
                "sport_category": "2 разряд",
                "certificate_id": "FSP-SIB-2025-0091",
            },
            {
                "id": "ach-2024-2",
                "event_name": "Региональный отборочный тур Чемпионата России 2024",
                "event_date": "2024-09-01T10:00:00Z",
                "discipline": "Продуктовое программирование",
                "level": "REGIONAL",
                "result": "PARTICIPANT",
                "sport_category": None,
                "certificate_id": "FSP-REG-2024-0551",
            },
        ],
    },
}


def _generate_synthetic_participant(fsp_id: str) -> dict[str, Any] | None:
    """Generates deterministic achievements for any arbitrary FSP-XXXX ID for demo flexibility."""
    if not fsp_id.upper().startswith("FSP-"):
        return None
    # Special ID meaning candidate is not in the registry
    if fsp_id.upper() in ("FSP-NONE", "FSP-0000", "FSP-NOTFOUND"):
        return None

    # Deterministic hash to seed achievements
    seed_val = sum(ord(c) for c in fsp_id)
    ranks = ["КМС", "1 разряд", "2 разряд", "Мастер спорта"]
    assigned_rank = ranks[seed_val % len(ranks)]

    events = [
        (
            "Хакатон «Лидеры цифровой трансформации» (ЛЦТ)",
            "Продуктовое программирование",
            "ALL_RUSSIAN",
            "PRIZE_WINNER" if seed_val % 2 == 0 else "FINALIST",
        ),
        (
            "Чемпионат России по спортивному программированию",
            "Алгоритмическое программирование",
            "ALL_RUSSIAN",
            "WINNER" if seed_val % 3 == 0 else "PARTICIPANT",
        ),
    ]

    achievements = []
    for idx, (ev_name, disc, lvl, res) in enumerate(events):
        achievements.append({
            "id": f"ach-synth-{seed_val}-{idx}",
            "event_name": f"{ev_name} 2025",
            "event_date": "2025-08-10T10:00:00Z",
            "discipline": disc,
            "level": lvl,
            "result": res,
            "sport_category": assigned_rank if idx == 0 else None,
            "certificate_id": f"FSP-SYNTH-{seed_val}-{idx}",
        })

    return {
        "fsp_id": fsp_id,
        "full_name": f"Спортсмен {fsp_id}",
        "region": "РФ",
        "current_sport_rank": assigned_rank,
        "status": "ACTIVE",
        "achievements": achievements,
    }


@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint for container orchestrators and readiness probes."""
    return {
        "status": "ok",
        "service": "fsp-registry-mock",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get(
    "/fsp-registry/participants/{fsp_id}/achievements",
    response_model=FSPParticipantProfile,
    tags=["Registry"],
    summary="Получить спортивные достижения участника по FSP ID",
)
def get_participant_achievements(
    fsp_id: str = Path(..., description="Идентификатор спортсмена в реестре (например, FSP-1001)"),
):
    """Возвращает информацию о спортсмене и верифицированные достижения.

    Если спортсмен не найден в реестре, возвращает HTTP 404.
    """
    normalized_id = fsp_id.strip()
    if normalized_id in MOCK_PARTICIPANTS:
        return MOCK_PARTICIPANTS[normalized_id]

    synthetic = _generate_synthetic_participant(normalized_id)
    if synthetic:
        return synthetic

    raise HTTPException(
        status_code=404,
        detail={
            "error_code": "FSP_PARTICIPANT_NOT_FOUND",
            "message": f"Спортсмен с идентификатором {fsp_id} не найден в реестре ФСП.",
        },
    )
