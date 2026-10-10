"""Explainable Candidate Matching and Two-Stage Ranking Engine.

Stage 1: Multi-criteria pool filtering
  - Category filtering (target category, adjacent grade, related specialization)
  - Work format compatibility (REMOTE, HYBRID, OFFICE)
  - City filtering
  - Salary budget boundary (desired_salary_min <= budget_max)
  - Privacy flags (status != 'HIDDEN')

Stage 2: Explainable Ranking Formula (DEFAULT_WEIGHTS, overridable for validation):
  Score = 0.30*C + 0.25*S + 0.10*E + 0.25*T + 0.07*F + 0.03*A

Where:
  C = Category match (1.0 exact, 0.6 adjacent grade, 0.4 related specialization, 0.1 other)
  S = Stack coverage with verification weights (1.0 test/FSP, 0.5 resume, 0.3 claimed, 0.0 missing)
  E = Semantic similarity (keyword overlap / Jaccard similarity in [0..1])
  T = Test percentile inside category (0..1)
  F = FSP score (0..1; if no FSP history, F=0 without penalty)
  A = Recency / activity (0..1)

Explainability:
  Produces 3-4 human-readable justification bullet points per ranked candidate.
"""

import math
import re
from datetime import datetime, timezone
from typing import Any

from scipy.stats import norm

from backend.app.models.candidate import CandidateProfile
from backend.app.modules.fsp.score import format_fsp_ranking_bullet, get_discipline_relevance

# Grade ranks mapping for adjacent grade determination
GRADE_RANKS: dict[str, int] = {
    "INTERN": 1,
    "СТАЖЕР": 1,
    "СТАЖЁР": 1,
    "JUNIOR": 2,
    "ДЖУНИОР": 2,
    "МЛАДШИЙ": 2,
    "MIDDLE": 3,
    "МИДЛ": 3,
    "SENIOR": 4,
    "СЕНЬОР": 4,
    "СТАРШИЙ": 4,
    "LEAD": 5,
    "ЛИД": 5,
    "ВЕДУЩИЙ": 5,
}

# Related specializations graph (codes from the specializations dictionary; Backend <-> DevOps, Data <-> Backend per plan 4.1)
RELATED_SPECS: dict[str, set[str]] = {
    "BACKEND": {"DEVOPS", "QA", "QA_AUTOMATION", "DATA_ML", "DATA_ENGINEER", "FULLSTACK"},
    "FRONTEND": {"MOBILE", "FULLSTACK", "UI_UX", "WEB"},
    "QA": {"QA_AUTOMATION", "BACKEND", "MANUAL_QA"},
    "DATA_ML": {"BACKEND", "ML_ENGINEER", "DATA_ENGINEER", "ANALYST", "AI_ENGINEER"},
    "DEVOPS": {"BACKEND", "SYSADMIN", "SRE", "INFRASTRUCTURE"},
}

# Ranking formula weights (plan 4.4); validation tunes them on dev needs
DEFAULT_WEIGHTS: dict[str, float] = {"C": 0.30, "S": 0.25, "E": 0.10, "T": 0.25, "F": 0.07, "A": 0.03}

# Penalty factor for unconfirmed grade per Q&A: unconfirmed candidates are not hidden,
# but are displayed with status and lowered in search ranking
UNCONFIRMED_GRADE_FACTOR: float = 0.60

# How much a skill counts towards stack coverage depending on how it was confirmed
SKILL_SOURCE_WEIGHTS: dict[str, float] = {"ASSESSMENT": 1.0, "TEST": 1.0, "FSP": 1.0, "RESUME": 0.5, "CLAIMED": 0.3}
VERIFIED_SKILL_SOURCES = frozenset({"ASSESSMENT", "TEST", "FSP"})


def is_unconfirmed_grade(grade_str: str | None) -> bool:
    """Checks whether a candidate's grade is unconfirmed."""
    if not grade_str or not grade_str.strip():
        return True
    clean = grade_str.strip().upper()
    return clean in {
        "UNCONFIRMED",
        "НЕ_ПОДТВЕРЖДЕН",
        "НЕ ПОДТВЕРЖДЕН",
        "НЕ ПОДТВЕРЖДЁН",
        "НЕ_ПОДТВЕРЖДЁН",
        "НЕ ПОДТВЕРЖДЕННЫЙ",
        "NONE",
    }


def normalize_token(s: str) -> str:
    """Normalizes string for comparison."""
    if not s:
        return ""
    clean = re.sub(r"[^\w\s\+\#]", " ", s.lower())
    return " ".join(clean.split())


def skills_match(required: str, have: str) -> bool:
    """Whole-word match of normalized skill names.

    "spring" matches "spring boot" and "go" matches "go golang", but "java" does not match
    "javascript" and "go" does not match "django" or "mongodb".
    """
    if not required or not have:
        return False
    if required == have:
        return True
    shorter, longer = sorted((required, have), key=len)
    return re.search(rf"(?<![\w+#]){re.escape(shorter)}(?![\w+#])", longer) is not None


def get_grade_rank(grade_str: str | None) -> int:
    if not grade_str:
        return 3
    clean = grade_str.strip().upper()
    for k, v in GRADE_RANKS.items():
        if k in clean:
            return v
    return 3


def is_adjacent_grade(cand_grade: str | None, target_grade: str | None) -> bool:
    r_cand = get_grade_rank(cand_grade)
    r_target = get_grade_rank(target_grade)
    return abs(r_cand - r_target) == 1


def is_related_specialization(cand_spec: str | None, target_spec: str | None) -> bool:
    if not cand_spec or not target_spec:
        return False
    c_cand = cand_spec.strip().upper().replace(" ", "_")
    c_target = target_spec.strip().upper().replace(" ", "_")
    if c_cand == c_target:
        return True
    for key, related in RELATED_SPECS.items():
        if key in c_target and any(r in c_cand for r in related):
            return True
        if key in c_cand and any(r in c_target for r in related):
            return True
    return False


# ==========================================
# STAGE 1: FILTERING
# ==========================================

def filter_candidate_pool(
    candidates: list[CandidateProfile],
    target_specialization: str | None = None,
    target_grade: str | None = None,
    work_format: str | None = None,
    city: str | None = None,
    salary_budget_max: int | None = None,
    allow_adjacent_grades: bool = True,
    allow_related_specs: bool = True,
    has_fsp: bool | None = None,
    required_skills: list[str] | None = None,
    strict_filters: bool = False,
) -> list[CandidateProfile]:
    """Stage 1: Filters the candidate pool down to eligible candidates."""
    filtered: list[CandidateProfile] = []

    for cand in candidates:
        # 1. Privacy filter: Hidden candidates are excluded from employer search
        if cand.status == "HIDDEN":
            continue

        # 2. Desired salary filter: candidate's minimum desired salary must not exceed employer max budget
        if salary_budget_max and cand.desired_salary_min:
            if cand.desired_salary_min > salary_budget_max:
                continue

        # 3. Work format & city filter
        if work_format:
            wf_req = work_format.strip().upper()
            cand_wf = (cand.work_format or "REMOTE").strip().upper()
            if wf_req != "REMOTE":
                # If employer requires OFFICE or HYBRID in a specific city
                if city and cand.city and cand_wf != "REMOTE":
                    c_cand_city = cand.city.strip().lower()
                    c_req_city = city.strip().lower()
                    if c_cand_city != c_req_city:
                        continue
            # If candidate is strictly OFFICE, but need is REMOTE
            if cand_wf == "OFFICE" and wf_req == "REMOTE":
                continue

        # 4. Specialization & Grade pool eligibility
        if target_specialization or target_grade:
            cand_spec = cand.confirmed_specialization or ""
            cand_gr = cand.confirmed_grade or ""

            cand_unconfirmed = is_unconfirmed_grade(cand_gr)

            spec_match = (
                not target_specialization
                or (cand_spec.strip().upper() == target_specialization.strip().upper())
            )
            spec_related = allow_related_specs and is_related_specialization(cand_spec, target_specialization)

            exact_grade = (
                not target_grade
                or (cand_gr.strip().upper() == target_grade.strip().upper())
            )
            adj_grade = allow_adjacent_grades and is_adjacent_grade(cand_gr, target_grade)

            # Accept if:
            # - exact match, or related spec with acceptable grade, or adjacent grade in same spec
            # - OR unconfirmed grade per Q&A requirement: do not hide unconfirmed grade candidates!
            #   They are retained and ranked with unconfirmed status and a penalty discount.
            is_category_eligible = (
                (spec_match and (exact_grade or adj_grade or cand_unconfirmed))
                or (spec_related and (exact_grade or adj_grade or cand_unconfirmed))
                or (not target_specialization and (exact_grade or adj_grade or cand_unconfirmed))
            )
            if not is_category_eligible:
                continue

        # 5. FSP achievements filter (if has_fsp is True: filter those who have fsp_score > 0 or is_fsp_verified)
        if has_fsp is True:
            f_score = getattr(cand, "fsp_score", 0.0) or 0.0
            is_fsp = getattr(cand, "is_fsp_verified", False) or False
            if not (f_score > 0.0 or is_fsp):
                continue

        if strict_filters and required_skills:
            cand_skills = [normalize_token(cs.skill.name) for cs in cand.skills if cs.skill]
            has_all_skills = True
            for req_skill in required_skills:
                req_norm = normalize_token(req_skill)
                if not any(skills_match(req_norm, cs) for cs in cand_skills):
                    has_all_skills = False
                    break
            if not has_all_skills:
                continue

        filtered.append(cand)

    return filtered


# ==========================================
# STAGE 2: EXPLAINABLE RANKING
# ==========================================

def compute_category_score(
    cand: CandidateProfile,
    target_specialization: str | None,
    target_grade: str | None,
) -> tuple[float, str]:
    """C: Category match (1.0 exact, 0.6 adjacent grade, 0.4 related specialization, 0.1 other)."""
    if not target_specialization and not target_grade:
        return 1.0, "Категория: критерии специализации не заданы (100% совпадение)"

    cand_spec = (cand.confirmed_specialization or "").strip().upper()
    cand_unconfirmed = is_unconfirmed_grade(cand.confirmed_grade)
    
    # If unconfirmed, use declared_grade for matching logic
    if cand_unconfirmed:
        cand_grade = (getattr(cand, "declared_grade", None) or cand.confirmed_grade or "").strip().upper()
    else:
        cand_grade = (cand.confirmed_grade or "").strip().upper()
        
    req_spec = (target_specialization or "").strip().upper()
    req_grade = (target_grade or "").strip().upper()

    spec_exact = (not req_spec) or (cand_spec == req_spec)
    grade_exact = (not req_grade) or (cand_grade == req_grade)

    base_score = 0.1
    reason = f"Категория: частичное соответствие ({cand.confirmed_category or 'Общий профиль'})"

    if spec_exact and grade_exact:
        cat_name = cand.confirmed_category or f"{cand_spec} · {cand_grade}"
        base_score = 1.0
        reason = f"Категория {cat_name} — точное совпадение"
    elif spec_exact and is_adjacent_grade(cand_grade, req_grade):
        base_score = 0.6
        reason = f"Категория: смежный грейд ({cand_grade} при запросе {req_grade})"
    elif is_related_specialization(cand_spec, req_spec) and (grade_exact or is_adjacent_grade(cand_grade, req_grade)):
        base_score = 0.4
        reason = f"Категория: смежная специализация ({cand_spec} к {req_spec})"

    if cand_unconfirmed:
        return base_score * UNCONFIRMED_GRADE_FACTOR, f"{reason} (штраф за неподтверждённый грейд)"
    
    return base_score, reason


def compute_stack_score(
    cand: CandidateProfile,
    required_skills: list[str],
    source_weights: dict[str, float] = SKILL_SOURCE_WEIGHTS,
) -> tuple[float, str]:
    """S: Stack coverage with verification weights.

    - 1.0: Verified by test (ASSESSMENT) or FSP
    - 0.5: Resume (RESUME)
    - 0.3: Self-claimed (CLAIMED)
    - 0.0: Missing
    """
    if not required_skills:
        return 0.5, "Стек: обязательные навыки не специфицированы"

    # Map candidate's skills to highest confirmation weight
    cand_skill_map: dict[str, tuple[float, str]] = {}
    for cs in getattr(cand, "skills", []):
        sk_name = ""
        if hasattr(cs, "skill") and cs.skill:
            sk_name = cs.skill.name
        elif hasattr(cs, "skill_name"):
            sk_name = cs.skill_name

        if not sk_name:
            continue

        norm_name = normalize_token(sk_name)
        src = (cs.confirmation_source or "CLAIMED").upper()
        w = source_weights.get(src, source_weights["CLAIMED"])

        if norm_name not in cand_skill_map or w > cand_skill_map[norm_name][0]:
            cand_skill_map[norm_name] = (w, src)

    total_weight = 0.0
    verified_count = 0
    covered_count = 0
    verified_names = []

    for req_sk in required_skills:
        norm_req = normalize_token(req_sk)
        matched_weight = 0.0
        matched_source = ""

        for cand_norm, (w, src) in cand_skill_map.items():
            if skills_match(norm_req, cand_norm) and w > matched_weight:
                matched_weight = w
                matched_source = src

        total_weight += matched_weight
        if matched_weight > 0.0:
            covered_count += 1
        if matched_source in VERIFIED_SKILL_SOURCES:
            verified_count += 1
            verified_names.append(req_sk)

    req_len = len(required_skills)
    s_score = min(1.0, max(0.0, total_weight / req_len))

    if verified_count == req_len:
        explanation = f"Стек: {verified_count} из {req_len} ключевых навыков подтверждены тестом"
    elif verified_count > 0:
        names_str = ", ".join(verified_names[:3])
        explanation = f"Стек: {verified_count} из {req_len} подтверждены тестом ({names_str})"
    elif covered_count > 0:
        explanation = f"Стек: {covered_count} из {req_len} указаны в резюме/профиле"
    else:
        explanation = "Стек: требуется дополнительная проверка стека"

    return round(s_score, 4), explanation


def compute_semantic_score(
    cand: CandidateProfile,
    title: str | None,
    description: str | None,
    required_skills: list[str],
) -> tuple[float, str]:
    """E: Semantic similarity (keyword overlap / Jaccard similarity in [0..1])."""
    text_corpus = " ".join(filter(None, [title, description] + required_skills))
    tokens_need = set(normalize_token(text_corpus).split())
    if not tokens_need:
        return 0.5, "Семантика: нейтральное совпадение контекста"

    cand_texts = [
        cand.confirmed_category,
        cand.confirmed_specialization,
        cand.city,
    ]
    for cs in getattr(cand, "skills", []):
        if hasattr(cs, "skill") and cs.skill:
            cand_texts.append(cs.skill.name)
    for ach in getattr(cand, "fsp_achievements", []):
        cand_texts.append(ach.event_name)
        cand_texts.append(ach.discipline)

    tokens_cand = set(normalize_token(" ".join(filter(None, cand_texts))).split())
    if not tokens_cand:
        return 0.2, "Семантика: базовый профиль"

    overlap = len(tokens_need.intersection(tokens_cand))
    jaccard = overlap / max(1, len(tokens_need.union(tokens_cand)))
    # Sublinear scaling so moderate overlap gives reasonable score
    sem_score = min(1.0, max(0.0, math.sqrt(jaccard) * 1.5))
    return round(sem_score, 4), f"Семантическое совпадение с описанием: {int(sem_score * 100)}%"


def compute_test_score(cand: CandidateProfile) -> tuple[float, str]:
    """T: Test percentile inside category (0..1)."""
    if cand.category_percentile and cand.category_percentile > 0:
        pct = max(1, min(99, cand.category_percentile))
        t_score = pct / 100.0
        # Φ(θ̂) over the specialization's population: within one category it orders candidates exactly by θ̂
        return round(t_score, 4), f"Тест: {pct}-й процентиль по специализации (адаптивный CAT)"

    # Fallback to theta if percentile not set
    if cand.last_theta is not None and abs(cand.last_theta) > 1e-4:
        pct = int(round(norm.cdf(cand.last_theta) * 100))
        pct = max(1, min(99, pct))
        t_score = pct / 100.0
        return round(t_score, 4), f"Тест: {pct}-й процентиль (оценка способности θ={cand.last_theta:+.2f})"

    return 0.50, "Тест: базовый уровень (прохождение CAT не завершено)"


def compute_activity_score(cand: CandidateProfile, now: datetime | None = None) -> tuple[float, str]:
    """A: Recency / activity score (0..1)."""
    if now is None:
        now = datetime.now(timezone.utc)

    status_base = 1.0 if cand.status == "ACTIVELY_SEARCHING" else (0.75 if cand.status == "OPEN" else 0.40)

    # Recency decay based on updated_at
    days_passed = 0
    if cand.updated_at:
        up_date = cand.updated_at
        if up_date.tzinfo is None:
            up_date = up_date.replace(tzinfo=timezone.utc)
        days_passed = max(0, (now - up_date).days)

    recency_factor = math.exp(-0.01 * days_passed)  # Half life ~ 70 days
    a_score = min(1.0, max(0.2, status_base * recency_factor))

    if cand.status == "ACTIVELY_SEARCHING":
        status_text = "в активном поиске"
    elif cand.status == "OPEN":
        status_text = "рассматривает предложения"
    else:
        status_text = "обновлен недавно"

    return round(a_score, 4), f"Активность: {status_text} (рейтинг актуальности {int(a_score*100)}%)"


def rank_and_explain_candidate(
    cand: CandidateProfile,
    target_specialization: str | None = None,
    target_grade: str | None = None,
    required_skills: list[str] | None = None,
    need_title: str | None = None,
    need_description: str | None = None,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Computes the 6-component explainable score for a single candidate.

    Formula (DEFAULT_WEIGHTS):
      Score = 0.30*C + 0.25*S + 0.10*E + 0.25*T + 0.07*F + 0.03*A
    """
    req_skills = required_skills or []
    w = weights or DEFAULT_WEIGHTS

    # 1. Category (C, weight 0.30)
    c_score, c_exp = compute_category_score(cand, target_specialization, target_grade)

    # 2. Stack coverage (S, weight 0.25)
    s_score, s_exp = compute_stack_score(cand, req_skills)

    # 3. Semantic similarity (E, weight 0.10)
    e_score, e_exp = compute_semantic_score(cand, need_title, need_description, req_skills)

    # 4. Test percentile (T, weight 0.25)
    t_score, t_exp = compute_test_score(cand)

    # 5. FSP score (F, weight 0.07 - Bonus without penalty!)
    f_score = getattr(cand, "fsp_score", 0.0) or 0.0
    f_score = max(0.0, min(1.0, float(f_score)))
    f_registry = f_score  # the badge describes the registry result, not the ranking bonus

    # FSP achievement bullet and discipline affinity bonus per Q&A Row 1
    achievements_list = [
        {
            "event_name": a.event_name,
            "level": a.level,
            "result": a.result,
            "discipline": a.discipline,
        }
        for a in getattr(cand, "fsp_achievements", [])
    ]
    sport_rank = next((a.sport_category for a in getattr(cand, "fsp_achievements", []) if a.sport_category), None)

    # Check if sport discipline aligns with target specialization (Q&A Row 1)
    has_spec_affinity = False
    if target_specialization and achievements_list:
        if any(get_discipline_relevance(a.get("discipline"), target_specialization) > 1.0 for a in achievements_list):
            has_spec_affinity = True
            f_score = min(1.0, f_score * 1.15)

    f_exp = format_fsp_ranking_bullet(f_score, achievements_list, sport_rank)
    if has_spec_affinity and f_score > 0.01:
        f_exp += " (профильная дисциплина ФСП)"

    # 6. Activity / Recency (A, weight 0.03)
    a_score, a_exp = compute_activity_score(cand, now)

    # Final Weighted Score Calculation
    components = {"C": c_score, "S": s_score, "E": e_score, "T": t_score, "F": f_score, "A": a_score}
    total_score = sum(w[k] * components[k] for k in DEFAULT_WEIGHTS)
    total_score = round(min(1.0, max(0.0, total_score)), 4)

    # Unconfirmed grade penalty (Q&A: show with unconfirmed status and lower in ranking)
    cand_unconfirmed = is_unconfirmed_grade(cand.confirmed_grade)
    
    # Assemble key highlight bullets for employer card
    bullets = [c_exp, s_exp, t_exp, f_exp]
    if cand_unconfirmed:
        bullets.append("Квалификация: грейд не подтверждён тестом (понижен в поисковой выдаче)")

    return {
        "candidate_id": cand.id,
        "total_score": total_score,
        "score_percent": int(round(total_score * 100)),
        "is_grade_confirmed": not cand_unconfirmed,
        "grade_status": "UNCONFIRMED" if cand_unconfirmed else "CONFIRMED",
        "components": {k: round(v, 4) for k, v in components.items()},
        "weights": dict(w),
        "bullet_points": bullets,
        "fsp_badge": (
            "Победитель ФСП" if f_registry >= 0.8
            else ("Призёр ФСП" if f_registry >= 0.5
            else ("Спортсмен ФСП" if f_registry > 0.0 else "Без спортивной истории"))
        ),
    }


def execute_two_stage_matching(
    all_candidates: list[CandidateProfile],
    target_specialization: str | None = None,
    target_grade: str | None = None,
    required_skills: list[str] | None = None,
    work_format: str | None = None,
    city: str | None = None,
    salary_budget_max: int | None = None,
    need_title: str | None = None,
    need_description: str | None = None,
    top_limit: int = 50,
    weights: dict[str, float] | None = None,
    has_fsp: bool | None = None,
    strict_filters: bool = False,
) -> list[dict[str, Any]]:
    """Runs Stage 1 filtering followed by Stage 2 scoring and ranking."""
    # Stage 1: Pool filtering
    eligible_candidates = filter_candidate_pool(
        candidates=all_candidates,
        target_specialization=target_specialization,
        target_grade=target_grade,
        work_format=work_format,
        city=city,
        salary_budget_max=salary_budget_max,
        allow_adjacent_grades=not strict_filters,
        allow_related_specs=not strict_filters,
        has_fsp=has_fsp,
        required_skills=required_skills,
        strict_filters=strict_filters,
    )

    # Stage 2: Scoring each candidate
    ranked_results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for cand in eligible_candidates:
        cand_ranked = rank_and_explain_candidate(
            cand=cand,
            target_specialization=target_specialization,
            target_grade=target_grade,
            required_skills=required_skills,
            need_title=need_title,
            need_description=need_description,
            now=now,
            weights=weights,
        )

        salary_type_val = getattr(cand, "salary_type", "NET") or "NET"
        is_gross_val = getattr(cand, "is_gross", False) or (salary_type_val == "GROSS")
        salary_disp = None
        if cand.desired_salary_min:
            label = " (до вычета НДФЛ / Гросс)" if is_gross_val else " (на руки / Нетто)"
            salary_disp = f"{cand.desired_salary_min:,} ₽{label}".replace(",", " ")

        cand_unconfirmed = is_unconfirmed_grade(cand.confirmed_grade)

        full_name_val = None
        fn = getattr(cand, "first_name", "") or ""
        ln = getattr(cand, "last_name", "") or ""
        full_name_val = f"{fn} {ln}".strip()
        
        if not full_name_val:
            full_name_val = getattr(cand, "full_name", None) or f"Кандидат #{cand.id[:8]}"

        # Pack anonymized candidate card (contacts hidden, name/experience visible per Q&A)
        cand_ranked["candidate_card"] = {
            "id": cand.id,
            "full_name": full_name_val,
            "confirmed_category": cand.confirmed_category,
            "confirmed_specialization": cand.confirmed_specialization,
            "confirmed_grade": cand.confirmed_grade or "Не подтверждён",
            "is_grade_confirmed": not cand_unconfirmed,
            "grade_status": "UNCONFIRMED" if cand_unconfirmed else "CONFIRMED",
            "grade_status_display": "Не подтверждён" if cand_unconfirmed else "Подтверждён",
            "declared_grade": getattr(cand, "declared_grade", None),
            "category_percentile": cand.category_percentile,
            "fsp_score": cand.fsp_score or 0.0,
            "is_fsp_verified": cand.is_fsp_verified or False,
            "desired_salary_min": cand.desired_salary_min,
            "salary_type": salary_type_val,
            "is_gross": is_gross_val,
            "salary_display": salary_disp,
            "work_format": cand.work_format,
            "city": cand.city,
            "contacts_hidden": True,  # 152-FZ contact privacy
        }
        ranked_results.append(cand_ranked)

    # Sort descending by total score
    ranked_results.sort(key=lambda x: x["total_score"], reverse=True)

    # Assign 1-based ranks
    for idx, item in enumerate(ranked_results, start=1):
        item["rank"] = idx

    return ranked_results[:top_limit]
