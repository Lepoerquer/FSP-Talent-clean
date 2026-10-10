"""FSP Score calculation engine and sport achievements valuation.

Formula:
  RawScore = sum(Level * Result * DisciplineRelevance * Decay) + SportCategoryBonus
  NormalizedScore = log(1 + RawScore) / log(1 + MaxExpectedScore), clipped to [0.0, 1.0]

Special handling:
- Candidates with NO FSP history receive NormalizedScore = 0.0.
- They are displayed with the neutral badge "Без спортивной истории".
- They are NEVER penalized or blocked in matching.
"""

import math
from datetime import datetime, timezone
from typing import Any

# All competitions are equally valued (1.0) per Q&A guidelines:
# "Ранжировать дисциплины не надо: все соревнования равно важны,
# внутренний рейтинг «чемпионат России выше хакатона» давать не советуют".
LEVEL_WEIGHTS: dict[str, float] = {
    "INTERNATIONAL": 1.0,
    "МЕЖДУНАРОДНЫЙ": 1.0,
    "ALL_RUSSIAN": 1.0,
    "ВСЕРОССИЙСКИЙ": 1.0,
    "INTERREGIONAL": 1.0,
    "МЕЖРЕГИОНАЛЬНЫЙ": 1.0,
    "REGIONAL": 1.0,
    "РЕГИОНАЛЬНЫЙ": 1.0,
    "CITY": 1.0,
    "ГОРОДСКОЙ": 1.0,
}

RESULT_WEIGHTS: dict[str, float] = {
    "WINNER": 1.0,
    "ПОБЕДИТЕЛЬ": 1.0,
    "1ST_PLACE": 1.0,
    "1 МЕСТО": 1.0,
    "PRIZE_WINNER": 0.75,
    "ПРИЗЁР": 0.75,
    "ПРИЗЕР": 0.75,
    "2ND_PLACE": 0.75,
    "3RD_PLACE": 0.75,
    "2 МЕСТО": 0.75,
    "3 МЕСТО": 0.75,
    "FINALIST": 0.5,
    "ФИНАЛИСТ": 0.5,
    "PARTICIPANT": 0.2,
    "УЧАСТНИК": 0.2,
    "ОТБОР": 0.2,
}

# All official disciplines of the Russian Federation of Sports Programming (FSP)
# have equal value (1.0) according to definitive Q&A session decisions (no artificial hierarchy)
DISCIPLINE_WEIGHTS: dict[str, float] = {
    "ПРОДУКТОВОЕ ПРОГРАММИРОВАНИЕ": 1.0,
    "PRODUCT_PROGRAMMING": 1.0,
    "АЛГОРИТМИЧЕСКОЕ ПРОГРАММИРОВАНИЕ": 1.0,
    "ALGORITHMIC_PROGRAMMING": 1.0,
    "СПОРТИВНОЕ ПРОГРАММИРОВАНИЕ": 1.0,
    "SPORTS_PROGRAMMING": 1.0,
    "ПРОГРАММИРОВАНИЕ СИСТЕМ ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ": 1.0,
    "SECURITY_PROGRAMMING": 1.0,
    "РОБОТОТЕХНИКА": 1.0,
    "ROBOTICS": 1.0,
    "ПРОГРАММИРОВАНИЕ РОБОТОТЕХНИКИ": 1.0,
    "СИСТЕМНОЕ ПРОГРАММИРОВАНИЕ": 1.0,
}

SPORT_CATEGORY_BONUS: dict[str, float] = {
    "МСМК": 0.35,
    "МАСТЕР СПОРТА МЕЖДУНАРОДНОГО КЛАССА": 0.35,
    "МС": 0.25,
    "МАСТЕР СПОРТА": 0.25,
    "КМС": 0.15,
    "КАНДИДАТ В МАСТЕРА СПОРТА": 0.15,
    "1 РАЗРЯД": 0.10,
    "ПЕРВЫЙ РАЗРЯД": 0.10,
    "2 РАЗРЯД": 0.05,
    "ВТОРОЙ РАЗРЯД": 0.05,
    "3 РАЗРЯД": 0.02,
}

# Calibration constant: a candidate with 2 All-Russian wins + Candidate Master of Sports
# reaches ~2.5 raw score -> maps to ~1.0 normalized score.
MAX_EXPECTED_RAW_SCORE: float = 2.40
DECAY_LAMBDA: float = 0.22  # Half-life ~ 3.15 years


def get_level_weight(level: str | None) -> float:
    if not level:
        return 1.0
    return LEVEL_WEIGHTS.get(level.strip().upper(), 1.0)


def get_result_weight(result: str | None) -> float:
    if not result:
        return 0.2
    return RESULT_WEIGHTS.get(result.strip().upper(), 0.2)


DISCIPLINE_SPECIALIZATION_AFFINITY: dict[str, set[str]] = {
    "SECURITY_PROGRAMMING": {"SECURITY", "BACKEND", "DEVOPS", "SYSADMIN"},
    "ПРОГРАММИРОВАНИЕ СИСТЕМ ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ": {"SECURITY", "BACKEND", "DEVOPS", "SYSADMIN"},
    "PRODUCT_PROGRAMMING": {"BACKEND", "FRONTEND", "FULLSTACK", "MOBILE", "PRODUCT"},
    "ПРОДУКТОВОЕ ПРОГРАММИРОВАНИЕ": {"BACKEND", "FRONTEND", "FULLSTACK", "MOBILE", "PRODUCT"},
    "ALGORITHMIC_PROGRAMMING": {"BACKEND", "DATA_ML", "ALGORITHMS", "AI_ENGINEER"},
    "АЛГОРИТМИЧЕСКОЕ ПРОГРАММИРОВАНИЕ": {"BACKEND", "DATA_ML", "ALGORITHMS", "AI_ENGINEER"},
    "SPORTS_PROGRAMMING": {"BACKEND", "DATA_ML", "ALGORITHMS", "AI_ENGINEER"},
    "СПОРТИВНОЕ ПРОГРАММИРОВАНИЕ": {"BACKEND", "DATA_ML", "ALGORITHMS", "AI_ENGINEER"},
    "ROBOTICS": {"EMBEDDED", "HARDWARE", "ROBOTICS", "BACKEND"},
    "ПРОГРАММИРОВАНИЕ РОБОТОТЕХНИКИ": {"EMBEDDED", "HARDWARE", "ROBOTICS", "BACKEND"},
    "РОБОТОТЕХНИКА": {"EMBEDDED", "HARDWARE", "ROBOTICS", "BACKEND"},
}


def get_discipline_relevance(discipline: str | None, target_spec: str | None = None) -> float:
    """Calculates sport discipline relevance bonus per Q&A Row 1.
    All disciplines have equal baseline weight 1.0. If the candidate's sport discipline
    directly aligns with the requested specialization, returns 1.15 relevance boost.
    """
    if not discipline or not target_spec:
        return 1.0
    clean_disc = discipline.strip().upper()
    clean_spec = target_spec.strip().upper()
    affinities = DISCIPLINE_SPECIALIZATION_AFFINITY.get(clean_disc, set())
    if any(s in clean_spec or clean_spec in s for s in affinities):
        return 1.15
    return 1.0


def get_discipline_weight(discipline: str | None) -> float:
    """All disciplines have equal value (1.0) per Q&A guidelines."""
    if not discipline:
        return 1.0
    return DISCIPLINE_WEIGHTS.get(discipline.strip().upper(), 1.0)


def get_sport_category_bonus(category: str | None) -> float:
    if not category:
        return 0.0
    return SPORT_CATEGORY_BONUS.get(category.strip().upper(), 0.0)


def calculate_decay(event_date: datetime | None, now: datetime | None = None) -> float:
    """Calculates time decay multiplier based on the date of achievement."""
    if not event_date:
        return 0.8
    if now is None:
        now = datetime.now(timezone.utc)
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta_days = max(0, (now - event_date).days)
    delta_years = delta_days / 365.25
    return float(math.exp(-DECAY_LAMBDA * delta_years))


def calculate_achievement_weight(
    level: str | None,
    result: str | None,
    discipline: str | None,
    event_date: datetime | None = None,
    now: datetime | None = None,
    target_spec: str | None = None,
) -> float:
    """Calculates single achievement contribution: Level * Result * Discipline * Decay * Relevance."""
    w_level = get_level_weight(level)
    w_result = get_result_weight(result)
    w_discipline = get_discipline_weight(discipline)
    w_decay = calculate_decay(event_date, now)
    w_rel = get_discipline_relevance(discipline, target_spec)
    return round(w_level * w_result * w_discipline * w_decay * w_rel, 4)


def calculate_fsp_score(
    achievements: list[dict[str, Any]],
    sport_rank: str | None = None,
    now: datetime | None = None,
    target_spec: str | None = None,
) -> dict[str, Any]:
    """Calculates normalized FSP score and metadata.

    Args:
        achievements: List of achievement dictionaries with keys:
            level, result, discipline, event_date, sport_category.
        sport_rank: Optional overall sports category/rank (e.g. КМС).
        now: Current timestamp (for decay calculations).
        target_spec: Optional target specialization for domain affinity (Q&A Row 1).
    """
    if not achievements and not sport_rank:
        return {
            "raw_score": 0.0,
            "normalized_score": 0.0,
            "badge": "Без спортивной истории",
            "description": "Кандидат не привязал профиль ФСП. Оценивается на общих основаниях по результатам тестирования и стеку.",
            "has_history": False,
            "achievements_count": 0,
            "sport_rank": None,
        }

    sum_achievements = 0.0
    highest_bonus = get_sport_category_bonus(sport_rank)

    for ach in achievements:
        lvl = ach.get("level")
        res = ach.get("result")
        disc = ach.get("discipline")
        ev_date = ach.get("event_date")
        if isinstance(ev_date, str):
            try:
                ev_date = datetime.fromisoformat(ev_date.replace("Z", "+00:00"))
            except ValueError:
                ev_date = None

        weight = calculate_achievement_weight(lvl, res, disc, ev_date, now, target_spec)
        sum_achievements += weight

        # Also check sport category attached to achievement
        ach_cat = ach.get("sport_category")
        if ach_cat:
            highest_bonus = max(highest_bonus, get_sport_category_bonus(ach_cat))

    raw_score = sum_achievements + highest_bonus

    # Log-scale normalization to [0.0, 1.0]
    norm_denom = math.log(1.0 + MAX_EXPECTED_RAW_SCORE)
    norm_score = math.log(1.0 + raw_score) / norm_denom
    norm_score = max(0.0, min(1.0, norm_score))
    norm_score = round(norm_score, 4)

    # Human-readable badge determination
    has_winner = any(
        get_result_weight(a.get("result")) >= 0.95 for a in achievements
    )
    has_prize = any(
        get_result_weight(a.get("result")) >= 0.70 for a in achievements
    )

    if has_winner:
        badge = "Победитель соревнований ФСП"
    elif has_prize:
        badge = "Призёр соревнований ФСП"
    elif sport_rank in ("КМС", "Мастер спорта", "МСМК"):
        badge = f"Спортсмен ФСП ({sport_rank})"
    elif achievements:
        badge = "Участник соревнований ФСП"
    else:
        badge = "Разрядник ФСП"

    description = (
        f"Подтверждено {len(achievements)} достижений в реестре ФСП. "
        f"Спортивный балл: {norm_score:.2f}."
    )

    return {
        "raw_score": round(raw_score, 4),
        "normalized_score": norm_score,
        "badge": badge,
        "description": description,
        "has_history": True,
        "achievements_count": len(achievements),
        "sport_rank": sport_rank,
    }


def format_fsp_ranking_bullet(
    fsp_score: float,
    achievements: list[dict[str, Any]] | None = None,
    sport_rank: str | None = None,
) -> str:
    """Generates human-readable bullet point for explainability engine."""
    if fsp_score <= 0.001 or not achievements:
        return "ФСП: нейтральный профиль (оценивается по результату CAT-тестирования)"

    # Find highest achievement
    best_ach = None
    best_weight = -1.0
    for ach in achievements:
        w = get_level_weight(ach.get("level")) * get_result_weight(ach.get("result"))
        if w > best_weight:
            best_weight = w
            best_ach = ach

    if best_ach:
        ev_name = best_ach.get("event_name", "соревнований ФСП")
        res_raw = best_ach.get("result", "")
        res_text = "участник"
        if get_result_weight(res_raw) >= 0.95:
            res_text = "победитель"
        elif get_result_weight(res_raw) >= 0.70:
            res_text = "призёр"
        elif get_result_weight(res_raw) >= 0.45:
            res_text = "финалист"

        rank_str = f", {sport_rank}" if sport_rank else ""
        return f"ФСП: {res_text} {ev_name}{rank_str} (бонус к ранжированию)"

    if sport_rank:
        return f"ФСП: спортивный разряд {sport_rank} (бонус к ранжированию)"

    return f"ФСП: подтверждённый спортивный рейтинг ({fsp_score:.2f})"
