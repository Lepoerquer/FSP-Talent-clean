"""FastAPI router for Computerized Adaptive Testing (CAT) endpoints.

Access: a qualifying test is started and taken by the signed-in candidate only, for their own profile. The express
(demo) test needs no account: it always runs on the shared jury profile and never touches a candidate's grade or
attempt history.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.models.assessment import AssessmentSession
from backend.app.models.candidate import CandidateProfile
from backend.app.models.user import User
from backend.app.modules.assessment import service
from backend.app.modules.assessment.schemas import (
    AssessmentAnswerRequest,
    AssessmentAnswerResponse,
    AssessmentDemoStartRequest,
    AssessmentFinishResponse,
    AssessmentStartRequest,
    AssessmentStartResponse,
    GradeStatusResponse,
    SessionNextItemResponse,
)
from backend.app.modules.auth.service import get_current_candidate, get_optional_user

router = APIRouter(prefix="/assessments", tags=["Adaptive Assessment (CAT / IRT)"])
grade_router = APIRouter(prefix="/me/grade", tags=["Adaptive Assessment (CAT / IRT)"])

START_CONFLICTS = {
    401: {"description": "Квалификационный тест проходит только авторизованный кандидат (экспресс-тест доступен без входа)."},
    403: {"description": "Передан candidate_profile_id чужого профиля."},
    409: {
        "description": (
            "Попытка сейчас недоступна. detail.error_code: SESSION_IN_PROGRESS (detail.session_id — продолжить её), "
            "INITIAL_ATTEMPTS_EXHAUSTED или COOLDOWN (detail.available_at — когда станет можно)."
        )
    },
}
SESSION_ACCESS = {
    401: {"description": "Сессия квалификационного теста доступна только её владельцу."},
    404: {"description": "Сессия не найдена или принадлежит другому кандидату."},
}


def _candidate_of(db: Session, user: User | None) -> CandidateProfile:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Квалификационный тест проходит авторизованный кандидат. Экспресс-тест доступен без входа.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    profile = db.query(CandidateProfile).filter(CandidateProfile.user_id == user.id).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Тест проходит кандидат: у учётной записи нет профиля кандидата.")
    return profile


def _authorize_session(db: Session, session_id: str, user: User | None) -> None:
    """Express sessions are open; a qualifying session belongs to one candidate and is hidden from everyone else."""
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if session is None or session.is_demo:
        return  # the service answers 404 for a missing session
    profile = _candidate_of(db, user)
    if session.candidate_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Assessment session '{session_id}' not found.")


@router.post(
    "/start",
    response_model=AssessmentStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new adaptive assessment session",
    description=(
        "Initiates a 2PL IRT adaptive testing session for a chosen specialization and target grade for the signed-in "
        "candidate. Applies the attempt policy: up to 3 initial attempts within 7 days, the offered test one grade up "
        "or down is free for 24 hours and short, then one attempt per 90 days. "
        "Pass is_demo=true (or is_express=true) for an express 5-question test: it runs on the jury profile, needs no "
        "account and does not change the candidate's grade or attempts."
    ),
    responses=START_CONFLICTS,
)
def start_assessment(
    payload: AssessmentStartRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AssessmentStartResponse:
    if payload.is_demo or payload.is_express:
        req = payload.model_copy(update={"candidate_profile_id": None, "is_demo": True})
        return service.start_assessment_session(db=db, req=req)
    profile = _candidate_of(db, current_user)
    if payload.candidate_profile_id and payload.candidate_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Тест можно начать только для своего профиля.")
    return service.start_assessment_session(db=db, req=payload.model_copy(update={"candidate_profile_id": profile.id}))


@router.post(
    "/demo/start",
    response_model=AssessmentStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Экспресс-тест / Демо-режим для жюри (3-5 минут, 5 вопросов)",
    description=(
        "Запуск быстрого адаптивного теста (5 вопросов, 3-5 минут) для жюри и экспертов. "
        "Не требует регистрации, не сжигает попытки и не накладывает 90-дневный кулдаун."
    ),
)
def start_demo_assessment(
    payload: AssessmentDemoStartRequest,
    db: Session = Depends(get_db),
) -> AssessmentStartResponse:
    req = AssessmentStartRequest(
        specialization=payload.specialization,
        target_grade=payload.target_grade,
        is_demo=True,
    )
    return service.start_assessment_session(db=db, req=req)


@router.get(
    "/{session_id}/next",
    response_model=SessionNextItemResponse,
    summary="Get next adaptive item",
    description="Selects and renders the next isomorphic item dynamically based on Maximum Fisher Information.",
    responses=SESSION_ACCESS,
)
def get_next_item(
    session_id: str,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> SessionNextItemResponse:
    _authorize_session(db, session_id, current_user)
    return service.get_next_item_for_session(db=db, session_id=session_id)


@router.post(
    "/{session_id}/answer",
    response_model=AssessmentAnswerResponse,
    summary="Submit item answer",
    description="Evaluates answer correctness, re-estimates ability theta and SE via EAP, and checks stopping rules.",
    responses=SESSION_ACCESS,
)
def submit_answer(
    session_id: str,
    payload: AssessmentAnswerRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AssessmentAnswerResponse:
    _authorize_session(db, session_id, current_user)
    return service.record_candidate_answer(db=db, session_id=session_id, req=payload)


@router.post(
    "/{session_id}/finish",
    response_model=AssessmentFinishResponse,
    summary="Finish assessment and determine grade",
    description="Applies grade cut-scores, confirms grade, and sets cooldown period for profile.",
    responses=SESSION_ACCESS,
)
def finish_assessment(
    session_id: str,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AssessmentFinishResponse:
    _authorize_session(db, session_id, current_user)
    return service.finish_assessment_session(db=db, session_id=session_id)


@grade_router.get(
    "",
    response_model=GradeStatusResponse,
    summary="Категория и грейд кандидата: статус, история попыток, когда можно пересдать",
)
def read_grade_status(
    candidate_profile_id: str | None = Query(None, description="ID своего профиля (необязательно: берётся из токена)"),
    profile: CandidateProfile = Depends(get_current_candidate),
    db: Session = Depends(get_db),
) -> GradeStatusResponse:
    if candidate_profile_id and candidate_profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступен только статус своего профиля.")
    return service.get_grade_status(db=db, candidate_profile_id=profile.id)
