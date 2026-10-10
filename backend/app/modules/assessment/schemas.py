"""Pydantic schemas for CAT Assessment API endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class AssessmentStartRequest(BaseModel):
    """Payload to initiate a new adaptive assessment session."""
    candidate_profile_id: str | None = Field(
        None,
        description="Candidate profile UUID. Optional if session is run standalone or with auth token.",
    )
    specialization: str = Field(
        ...,
        description="Target specialization: BACKEND, FRONTEND, QA, DATA_ML",
        examples=["BACKEND"],
    )
    target_grade: str = Field(
        ...,
        description="Self-assessed target grade: INTERN, JUNIOR, MIDDLE, SENIOR",
        examples=["MIDDLE"],
    )
    track: str | None = Field(
        None,
        description="Optional survey track or direction code",
    )
    is_demo: bool = Field(
        False,
        description="Демо-режим / Экспресс-тест для жюри (3-5 минут, 5 вопросов, без кулдауна)",
    )
    is_express: bool = Field(
        False,
        description="Синоним is_demo: сокращенный экспресс-тест на 5 вопросов",
    )


class AssessmentDemoStartRequest(BaseModel):
    """Payload to start a quick 3-5 minute demo test for jury without registration."""
    specialization: str = Field(
        "BACKEND",
        description="Target specialization: BACKEND, FRONTEND, QA, DATA_ML",
        examples=["BACKEND"],
    )
    target_grade: str = Field(
        "MIDDLE",
        description="Self-assessed target grade: INTERN, JUNIOR, MIDDLE, SENIOR",
        examples=["MIDDLE"],
    )


class AssessmentStartResponse(BaseModel):
    """Response returned upon starting an assessment session."""
    session_id: str
    candidate_profile_id: str | None = None
    specialization: str
    target_grade: str
    status: str
    current_theta: float
    current_se: float
    items_count: int
    started_at: datetime
    attempt_kind: str = Field("INITIAL", description="INITIAL, FOLLOW_UP or CHANGE")
    max_items: int = Field(25, description="Upper bound on the number of items in this session")
    is_demo: bool = Field(False, description="Признак демо-сессии / экспресс-теста для жюри")


class SessionNextItemResponse(BaseModel):
    """Rendered next item presented to the candidate. Excludes answers and psychometric parameters."""
    session_id: str
    session_item_id: str
    family_code: str
    topic: str
    item_format: str
    seed: int
    item_index: int
    question_text: str
    code_snippet: str | None = None
    options: dict[str, str]
    is_finished: bool = False
    stopping_reason: str | None = None


class AssessmentAnswerRequest(BaseModel):
    """Candidate's response submission for the current item."""
    session_item_id: str | None = Field(
        None,
        description="ID of the SessionItem presented to candidate.",
    )
    response: str = Field(
        ...,
        description="Selected option key, e.g. 'A', 'B', 'C', 'D' or raw answer",
        examples=["A"],
    )
    response_time_seconds: float | None = Field(
        None,
        description="Time spent on the question in seconds",
        examples=[14.5],
    )


class AssessmentAnswerResponse(BaseModel):
    """Feedback on the recorded response and updated ability estimation."""
    session_id: str
    is_correct: bool
    current_theta: float
    current_se: float
    items_count: int
    is_finished: bool
    stopping_reason: str | None = None


class AssessmentFinishResponse(BaseModel):
    """Comprehensive assessment summary, confirmed grade, and cooldown date."""
    session_id: str
    status: str
    final_theta: float
    final_se: float
    items_count: int
    target_grade: str
    is_confirmed: bool
    confirmed_grade: str | None = None
    confirmed_category: str | None = None
    category_percentile: int | None = None
    recommendation: str
    suggested_grade: str | None = None
    explanation: str
    next_grade_change_available_at: datetime | None = None
    attempt_kind: str = Field("INITIAL", description="INITIAL, FOLLOW_UP or CHANGE")
    grade_applied: bool = Field(False, description="The result changed the candidate's confirmed grade")
    is_demo: bool = Field(False, description="Признак демо-сессии / экспресс-теста для жюри")
    follow_up: "FollowUpOffer | None" = None
    regular_attempt: "RegularAttempt | None" = None
    topic_profile: list["TopicProfileEntry"] = Field(default_factory=list)


class TopicProfileEntry(BaseModel):
    """Strength or growth area by topic, relative to the candidate's own theta."""
    topic: str
    items: int = Field(..., description="Answered items on the topic: with 2-4 items this is a hint, not a measurement")
    correct: int
    expected: float = Field(..., description="Correct answers the IRT model expects at the final theta")
    level: str = Field(..., description="STRONG, ON_LEVEL or GROWTH")


class FollowUpOffer(BaseModel):
    """The test offered right after a result: one grade up or down, free and short."""
    grade: str
    specialization: str
    available_until: datetime


class RegularAttempt(BaseModel):
    """Whether a regular (non-offered) attempt can be started now."""
    allowed: bool
    kind: str | None = Field(None, description="INITIAL (initial determination) or CHANGE (grade change)")
    reason: str = Field(..., description="ALLOWED, SESSION_IN_PROGRESS, INITIAL_ATTEMPTS_EXHAUSTED or COOLDOWN")
    message: str
    available_at: datetime | None = None
    initial_attempts_left: int | None = None


class AttemptSummary(BaseModel):
    session_id: str
    specialization: str
    target_grade: str
    status: str
    kind: str = Field(..., description="INITIAL, FOLLOW_UP or CHANGE")
    started_at: datetime
    finished_at: datetime | None = None
    items_count: int
    theta: float | None = None
    se: float | None = None
    is_confirmed: bool | None = None
    recommendation: str | None = None


class GradeChangeEntry(BaseModel):
    previous_grade: str | None = None
    new_grade: str
    specialization: str
    reason: str
    changed_at: datetime


class GradeStatusResponse(BaseModel):
    """The "категория и грейд" screen: status, history and when the grade can change (plan 4.2)."""
    candidate_profile_id: str
    confirmed_specialization: str | None = None
    confirmed_grade: str | None = None
    confirmed_category: str | None = None
    category_percentile: int | None = None
    theta: float | None = None
    se: float | None = None
    next_grade_change_available_at: datetime | None = None
    open_session_id: str | None = None
    regular_attempt: RegularAttempt
    follow_up: FollowUpOffer | None = None
    topic_profile: list[TopicProfileEntry] = Field(default_factory=list)
    attempts: list[AttemptSummary] = Field(default_factory=list)
    grade_history: list[GradeChangeEntry] = Field(default_factory=list)


AssessmentFinishResponse.model_rebuild()
