"""Grade determination rules and cut-scores for IRT-based assessment.

Cut-scores:
- Intern: -1.5
- Junior: -0.5
- Middle: +0.5
- Senior: +1.5

Rules:
1. theta >= cut_score -> grade confirmed.
2. theta - 1*SE >= next_grade_cut_score -> offer higher grade test.
3. theta < cut_score -> grade not confirmed; offer lower grade test (no forced downgrade).
4. After grade confirmation: set next_grade_change_available_at = now + 90 days.

Attempt policy (plan 4.3, see check_eligibility):
- initial determination: up to 3 attempts within 7 days of the first one, not counted as changes;
- the test offered right after a result (one grade up or down) is free for 24 hours and short;
- once a grade is confirmed and the initial window is over: one attempt per 90 days,
  and a failed attempt never lowers the current grade.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

GRADE_ORDER: list[str] = ["INTERN", "JUNIOR", "MIDDLE", "SENIOR"]

GRADE_CUT_SCORES: dict[str, float] = {
    "INTERN": -1.5,
    "JUNIOR": -0.5,
    "MIDDLE": 0.5,
    "SENIOR": 1.5,
}

# Centre of each grade band on the theta scale: the first item is selected here,
# so a declared Senior does not start with intern-level items.
GRADE_START_THETA: dict[str, float] = {
    "INTERN": -1.0,
    "JUNIOR": 0.0,
    "MIDDLE": 1.0,
    "SENIOR": 2.0,
}

GRADE_DISPLAY_NAMES: dict[str, str] = {
    "INTERN": "Стажер (Intern)",
    "JUNIOR": "Младший специалист (Junior)",
    "MIDDLE": "Специалист (Middle)",
    "SENIOR": "Ведущий специалист (Senior)",
}

GRADE_CHANGE_COOLDOWN_DAYS = 90


@dataclass
class AssessmentGradeEvaluation:
    """Psychometric grade evaluation result."""
    target_grade: str
    theta: float
    se: float
    cut_score: float
    is_confirmed: bool
    confirmed_grade: str | None
    recommendation: str  # GRADE_CONFIRMED, OFFER_HIGHER_GRADE, OFFER_LOWER_GRADE
    suggested_grade: str | None
    explanation: str
    next_grade_change_available_at: datetime | None


def normalize_grade(grade_str: str) -> str:
    """Normalize grade string to canonical uppercase code."""
    cleaned = grade_str.strip().upper()
    # Handle Russian mappings if passed
    ru_map = {
        "СТАЖЕР": "INTERN",
        "ДЖУНИОР": "JUNIOR",
        "МИДДЛ": "MIDDLE",
        "СЕНЬОР": "SENIOR",
        "СИНЬОР": "SENIOR",
    }
    return ru_map.get(cleaned, cleaned)


def get_cut_score(grade: str) -> float:
    """Retrieve cut-score for a grade level."""
    norm = normalize_grade(grade)
    if norm not in GRADE_CUT_SCORES:
        raise ValueError(f"Unknown grade level: '{grade}'. Valid: {list(GRADE_CUT_SCORES.keys())}")
    return GRADE_CUT_SCORES[norm]


def get_start_theta(grade: str) -> float:
    """Starting theta for item selection: the centre of the declared grade band."""
    norm = normalize_grade(grade)
    if norm not in GRADE_START_THETA:
        raise ValueError(f"Unknown grade level: '{grade}'. Valid: {list(GRADE_START_THETA.keys())}")
    return GRADE_START_THETA[norm]


def get_next_grade(grade: str) -> str | None:
    """Return the next higher grade, or None if already SENIOR."""
    norm = normalize_grade(grade)
    if norm not in GRADE_ORDER:
        return None
    idx = GRADE_ORDER.index(norm)
    if idx + 1 < len(GRADE_ORDER):
        return GRADE_ORDER[idx + 1]
    return None


def get_previous_grade(grade: str) -> str | None:
    """Return the next lower grade, or None if already INTERN."""
    norm = normalize_grade(grade)
    if norm not in GRADE_ORDER:
        return None
    idx = GRADE_ORDER.index(norm)
    if idx - 1 >= 0:
        return GRADE_ORDER[idx - 1]
    return None


def classify_theta_to_grade(theta: float) -> str:
    """Map continuous theta ability to the highest confirmed grade."""
    if theta >= GRADE_CUT_SCORES["SENIOR"]:
        return "SENIOR"
    if theta >= GRADE_CUT_SCORES["MIDDLE"]:
        return "MIDDLE"
    if theta >= GRADE_CUT_SCORES["JUNIOR"]:
        return "JUNIOR"
    return "INTERN"


def calculate_next_grade_cooldown(
    now: datetime | None = None,
    days: int = GRADE_CHANGE_COOLDOWN_DAYS,
) -> datetime:
    """Calculate future timestamp after which grade retake is unlocked."""
    if now is None:
        now = datetime.now(timezone.utc)
    return now + timedelta(days=days)


def evaluate_assessment_result(
    target_grade: str,
    theta: float,
    se: float,
    now: datetime | None = None,
) -> AssessmentGradeEvaluation:
    """Evaluate candidate's assessment result according to psychometric grade rules.

    Rules applied:
    - theta >= cut_score -> grade confirmed.
    - theta - 1*SE >= next_grade_cut_score -> offer higher grade test.
    - theta < cut_score -> grade not confirmed; offer lower grade test (no forced downgrade).
    - If confirmed: set next_grade_change_available_at = now + 90 days.

    Args:
        target_grade: Grade chosen or declared for this assessment.
        theta: Estimated ability parameter.
        se: Standard error of estimation.
        now: Timestamp reference for cooldown calculation.

    Returns:
        AssessmentGradeEvaluation with decisions and explanation.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    norm_target = normalize_grade(target_grade)
    cut = get_cut_score(norm_target)
    is_confirmed = theta >= cut

    if is_confirmed:
        # Grade confirmed!
        confirmed_grade = norm_target
        next_grade = get_next_grade(norm_target)
        cooldown = calculate_next_grade_cooldown(now)

        # Check if candidate exceeds grade boundaries with high statistical confidence
        if next_grade is not None:
            next_cut = get_cut_score(next_grade)
            # Conservative rule: lower 1-sigma bound exceeds next grade's cut-score
            if (theta - 1.0 * se) >= next_cut:
                return AssessmentGradeEvaluation(
                    target_grade=norm_target,
                    theta=theta,
                    se=se,
                    cut_score=cut,
                    is_confirmed=True,
                    confirmed_grade=confirmed_grade,
                    recommendation="OFFER_HIGHER_GRADE",
                    suggested_grade=next_grade,
                    explanation=(
                        f"Грейд {norm_target} уверенно подтвержден (θ={theta:.2f} >= {cut:.2f}). "
                        f"Показатели кандидата с учетом погрешности (θ - 1*SE = {theta - se:.2f}) "
                        f"превосходят порог следующего грейда {next_grade} ({next_cut:.2f}). "
                        f"Предложено пройти тестирование на грейд {next_grade}."
                    ),
                    next_grade_change_available_at=cooldown,
                )

        return AssessmentGradeEvaluation(
            target_grade=norm_target,
            theta=theta,
            se=se,
            cut_score=cut,
            is_confirmed=True,
            confirmed_grade=confirmed_grade,
            recommendation="GRADE_CONFIRMED",
            suggested_grade=norm_target,
            explanation=(
                f"Грейд {norm_target} успешно подтвержден! "
                f"Оценка способности θ={theta:.2f} (SE={se:.2f}) удовлетворяет порогу {cut:.2f}. "
                f"Повторное подтверждение доступно через {GRADE_CHANGE_COOLDOWN_DAYS} дней."
            ),
            next_grade_change_available_at=cooldown,
        )

    else:
        # Grade not confirmed. No forced downgrade!
        prev_grade = get_previous_grade(norm_target)
        return AssessmentGradeEvaluation(
            target_grade=norm_target,
            theta=theta,
            se=se,
            cut_score=cut,
            is_confirmed=False,
            confirmed_grade=None,  # No forced downgrade
            recommendation="OFFER_LOWER_GRADE",
            suggested_grade=prev_grade or norm_target,
            explanation=(
                f"Заявленный грейд {norm_target} не подтвержден: оценка θ={theta:.2f} ниже "
                f"квалификационного порога {cut:.2f}. В соответствии с правилами платформы "
                f"принудительное понижение грейда не производится. Кандидату предложено "
                f"пройти адаптивное тестирование на уровень "
                f"{prev_grade if prev_grade else norm_target}."
            ),
            next_grade_change_available_at=None,
        )


# ==========================================
# Category display
# ==========================================

SPECIALIZATION_SHORT_NAMES: dict[str, str] = {
    "BACKEND": "Backend",
    "FRONTEND": "Frontend",
    "QA": "QA",
    "DATA_ML": "Data/ML",
    "DEVOPS": "DevOps",
    "MOBILE": "Mobile",
}
GRADE_SHORT_NAMES: dict[str, str] = {"INTERN": "Стажёр", "JUNIOR": "Junior", "MIDDLE": "Middle", "SENIOR": "Senior"}


def normalize_specialization(specialization: str | None) -> str:
    """Profiles may hold "Backend" or "Data/ML" (seeded and demo data), sessions hold "BACKEND" or "DATA_ML"."""
    return (specialization or "").strip().upper().replace(" ", "_").replace("/", "_")


def format_category(specialization: str, grade: str) -> str:
    """Category label "специализация × грейд", e.g. "Backend · Middle" or "Data/ML · Senior"."""
    spec = specialization.upper().replace(" ", "_")
    norm = normalize_grade(grade)
    return f"{SPECIALIZATION_SHORT_NAMES.get(spec, spec.title())} · {GRADE_SHORT_NAMES.get(norm, norm.title())}"


# ==========================================
# Attempt policy
# ==========================================

INITIAL_MAX_ATTEMPTS = 3
INITIAL_WINDOW_DAYS = 7
# Not fixed by the plan: when the initial window ends without a confirmed grade, a new one opens
# this many days after it started. To confirm with the organizers.
RETRY_AFTER_UNCONFIRMED_DAYS = 30
FOLLOW_UP_WINDOW_HOURS = 24
FOLLOW_UP_MIN_ITEMS = 8
FOLLOW_UP_MAX_ITEMS = 15
# An unfinished session older than this is abandoned: it counts as an attempt and no longer blocks a new one
SESSION_ABANDON_HOURS = 3

KIND_INITIAL = "INITIAL"
KIND_FOLLOW_UP = "FOLLOW_UP"
KIND_CHANGE = "CHANGE"


def as_utc(moment: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything here is UTC."""
    if moment is None:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


@dataclass
class AttemptRecord:
    """One assessment session as the attempt policy sees it."""
    session_id: str
    target_grade: str
    status: str  # IN_PROGRESS, COMPLETED, ABANDONED
    started_at: datetime
    finished_at: datetime | None = None
    theta: float = 0.0
    se: float = 1.0
    specialization: str = ""

    def is_open(self, now: datetime) -> bool:
        return self.status == "IN_PROGRESS" and now - as_utc(self.started_at) < timedelta(hours=SESSION_ABANDON_HOURS)

    def evaluation(self) -> "AssessmentGradeEvaluation | None":
        if self.status != "COMPLETED":
            return None
        return evaluate_assessment_result(self.target_grade, self.theta, self.se, now=as_utc(self.finished_at))


def follow_up_offer(record: AttemptRecord) -> tuple[str, datetime] | None:
    """Grade the candidate may test right after `record`, and until when."""
    evaluation = record.evaluation()
    if evaluation is None or record.finished_at is None:
        return None
    if evaluation.recommendation not in ("OFFER_HIGHER_GRADE", "OFFER_LOWER_GRADE"):
        return None
    if evaluation.suggested_grade in (None, evaluation.target_grade):
        return None
    return evaluation.suggested_grade, as_utc(record.finished_at) + timedelta(hours=FOLLOW_UP_WINDOW_HOURS)


def is_follow_up(previous: AttemptRecord | None, record: AttemptRecord) -> bool:
    if previous is None:
        return False
    offer = follow_up_offer(previous)
    return (offer is not None
            and normalize_specialization(previous.specialization) == normalize_specialization(record.specialization)
            and normalize_grade(record.target_grade) == offer[0] and as_utc(record.started_at) <= offer[1])


@dataclass
class GradeStatus:
    """What the candidate may do now (plan 4.2, the "категория и грейд" screen)."""
    open_session_id: str | None
    follow_up_grade: str | None
    follow_up_specialization: str | None
    follow_up_until: datetime | None
    regular_allowed: bool
    regular_kind: str | None  # INITIAL or CHANGE
    reason: str  # ALLOWED, SESSION_IN_PROGRESS, INITIAL_ATTEMPTS_EXHAUSTED, COOLDOWN
    message: str
    available_at: datetime | None
    initial_attempts_left: int | None
    attempt_kinds: list[str]  # kind of every past record, chronological


def _attempt_kinds(records: Sequence[AttemptRecord], first_confirmed_at: datetime | None) -> tuple[list[str], datetime | None, int]:
    """Kind of each record, start of the latest attempt window and attempts in it."""
    kinds: list[str] = []
    window_start: datetime | None = None
    window_count = 0
    previous = None
    for record in records:
        if is_follow_up(previous, record):
            kinds.append(KIND_FOLLOW_UP)
        else:
            started = as_utc(record.started_at)
            if window_start is None or started >= window_start + timedelta(days=INITIAL_WINDOW_DAYS):
                window_start, window_count = started, 1
            else:
                window_count += 1
            confirmed_before = first_confirmed_at is not None and as_utc(first_confirmed_at) <= window_start
            kinds.append(KIND_CHANGE if confirmed_before else KIND_INITIAL)
        previous = record
    return kinds, window_start, window_count


def grade_status(
    records: Sequence[AttemptRecord],
    confirmed_grade: str | None,
    first_confirmed_at: datetime | None,
    next_change_at: datetime | None,
    now: datetime,
    confirmed_specialization: str | None = None,
) -> GradeStatus:
    """Attempt policy for a candidate given their sessions in chronological order.

    first_confirmed_at: when a grade was confirmed for the first time (None if never). A profile that
    has a grade without a recorded confirmation (seeded data) passes datetime.min.
    """
    now = as_utc(now)
    records = sorted(records, key=lambda r: as_utc(r.started_at))
    kinds, window_start, window_count = _attempt_kinds(records, first_confirmed_at)
    open_ids = [r.session_id for r in records if r.is_open(now)]

    follow_grade = follow_spec = follow_until = None
    if records:
        offer = follow_up_offer(records[-1])
        # no offer to test for the grade the candidate already holds (a Middle who failed Senior)
        holds_it = (offer is not None and confirmed_grade is not None and offer[0] == normalize_grade(confirmed_grade)
                    and normalize_specialization(records[-1].specialization) == normalize_specialization(confirmed_specialization))
        if offer and now <= offer[1] and not holds_it:
            (follow_grade, follow_until), follow_spec = offer, records[-1].specialization

    def result(allowed: bool, kind: str | None, reason: str, message: str,
               available_at: datetime | None = None, left: int | None = None) -> GradeStatus:
        if open_ids:
            return GradeStatus(open_ids[-1], None, None, None, False, kind, "SESSION_IN_PROGRESS",
                               "Есть незавершённое тестирование: продолжите его.", None, left, kinds)
        return GradeStatus(None, follow_grade, follow_spec, follow_until, allowed, kind, reason, message,
                           available_at, left, kinds)

    if window_start is None and first_confirmed_at is None:
        return result(True, KIND_INITIAL, "ALLOWED", "Можно пройти тест.", left=INITIAL_MAX_ATTEMPTS)
    window_open = window_start is not None and now < window_start + timedelta(days=INITIAL_WINDOW_DAYS)
    window_is_initial = window_start is not None and (
        first_confirmed_at is None or as_utc(first_confirmed_at) > window_start
    )
    if window_is_initial:
        if window_open and window_count < INITIAL_MAX_ATTEMPTS:
            return result(True, KIND_INITIAL, "ALLOWED",
                          "Идёт первичное определение грейда: попытки не считаются сменой.",
                          left=INITIAL_MAX_ATTEMPTS - window_count)
        if confirmed_grade is None:
            retry_at = window_start + timedelta(days=RETRY_AFTER_UNCONFIRMED_DAYS)
            if now >= retry_at:
                return result(True, KIND_INITIAL, "ALLOWED", "Можно снова пройти тест.", left=INITIAL_MAX_ATTEMPTS)
            return result(False, KIND_INITIAL, "INITIAL_ATTEMPTS_EXHAUSTED",
                          "Попытки первичного определения грейда закончились.", available_at=retry_at, left=0)
    next_change = as_utc(next_change_at)
    if next_change is None or now >= next_change:
        return result(True, KIND_CHANGE, "ALLOWED", "Можно пересдать тест для смены грейда.", left=0)
    return result(False, KIND_CHANGE, "COOLDOWN", "Грейд можно менять не чаще раза в 90 дней.",
                  available_at=next_change, left=0)


@dataclass
class Eligibility:
    allowed: bool
    kind: str | None
    reason: str
    message: str
    available_at: datetime | None = None
    open_session_id: str | None = None


def check_eligibility(status: GradeStatus, requested_grade: str, requested_specialization: str) -> Eligibility:
    """May the candidate start a test on `requested_grade` now, and as which kind of attempt."""
    grade = normalize_grade(requested_grade)
    if status.open_session_id:
        return Eligibility(False, None, status.reason, status.message, open_session_id=status.open_session_id)
    same_spec = normalize_specialization(status.follow_up_specialization) == normalize_specialization(requested_specialization)
    if status.follow_up_grade == grade and same_spec:
        return Eligibility(True, KIND_FOLLOW_UP, "ALLOWED",
                           f"Предложенный тест на грейд {grade}: не считается попыткой и проходит короче.")
    return Eligibility(status.regular_allowed, status.regular_kind, status.reason, status.message, status.available_at)
