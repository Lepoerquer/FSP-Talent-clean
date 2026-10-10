"""Business logic service for CAT Adaptive Assessment sessions."""

import json
import os
import random

# Import item bank registry
import sys
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.assessment import AssessmentSession, ItemFamily, SessionItem
from backend.app.models.candidate import CandidateProfile, GradeHistory
from backend.app.models.user import User
from backend.app.modules.assessment.cat_engine import (
    DEMO_MAX_ITEMS,
    DEMO_MIN_ITEMS,
    MAX_ITEMS,
    MIN_ITEMS,
    ItemCandidate,
    select_next_item,
    should_stop_assessment,
)
from backend.app.modules.assessment.grade_rules import (
    FOLLOW_UP_MAX_ITEMS,
    FOLLOW_UP_MIN_ITEMS,
    GRADE_CHANGE_COOLDOWN_DAYS,
    GRADE_START_THETA,
    KIND_CHANGE,
    KIND_FOLLOW_UP,
    KIND_INITIAL,
    AttemptRecord,
    GradeStatus,
    as_utc,
    check_eligibility,
    evaluate_assessment_result,
    format_category,
    get_start_theta,
    grade_status,
    is_follow_up,
    normalize_grade,
)
from backend.app.modules.assessment.irt import (
    calculate_category_percentile,
    estimate_theta_eap,
    topic_profile,
)
from backend.app.modules.assessment.schemas import (
    AssessmentAnswerRequest,
    AssessmentAnswerResponse,
    AssessmentFinishResponse,
    AssessmentStartRequest,
    AssessmentStartResponse,
    AttemptSummary,
    FollowUpOffer,
    GradeChangeEntry,
    GradeStatusResponse,
    RegularAttempt,
    SessionNextItemResponse,
    TopicProfileEntry,
)

BANK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "assessment-bank"))
if BANK_DIR not in sys.path:
    sys.path.insert(0, BANK_DIR)

from families.registry import FAMILIES_METADATA, render_family_item


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sync_item_families_to_db(db: Session) -> None:
    """Mirror the bank registry into the database.

    The registry owns content metadata (topic, grade, IRT parameters); the database owns
    exposure counters and the admin on/off switch. Families removed from the registry are
    deactivated, since there is no generator left to render them.
    """
    existing = {f.code: f for f in db.query(ItemFamily).all()}
    changed = False
    for code, family in existing.items():
        meta = FAMILIES_METADATA.get(code)
        if meta is None:
            if family.is_active:
                family.is_active = False
                changed = True
            continue
        fields = {
            "specialization": meta.specialization,
            "target_grade": meta.target_grade,
            "topic": meta.topic,
            "item_format": meta.item_format,
            "discrimination_a": meta.discrimination_a,
            "difficulty_b": meta.difficulty_b,
        }
        for attr, value in fields.items():
            if getattr(family, attr) != value:
                setattr(family, attr, value)
                changed = True

    for code, meta in FAMILIES_METADATA.items():
        if code not in existing:
            family_obj = ItemFamily(
                id=str(uuid.uuid4()),
                code=meta.code,
                specialization=meta.specialization,
                target_grade=meta.target_grade,
                topic=meta.topic,
                item_format=meta.item_format,
                discrimination_a=meta.discrimination_a,
                difficulty_b=meta.difficulty_b,
                exposure_count=0,
                is_active=True,
                template_yaml=f"code: {meta.code}\ndescription: {meta.description}\n",
                created_at=utcnow(),
            )
            db.add(family_obj)
            changed = True
    if changed:
        db.commit()


# ==========================================
# Attempt history and policy (grade_rules.grade_status)
# ==========================================

def _record(session: AssessmentSession) -> AttemptRecord:
    return AttemptRecord(session.id, session.target_grade, session.status, session.started_at, session.finished_at,
                         session.current_theta, session.current_se, session.specialization)


def _candidate_sessions(db: Session, candidate_profile_id: str) -> list[AssessmentSession]:
    """Qualifying sessions of a candidate. Express (demo) sessions are not attempts and never enter the policy."""
    sessions = (
        db.query(AssessmentSession)
        .filter(AssessmentSession.candidate_profile_id == candidate_profile_id, AssessmentSession.is_demo.is_not(True))
        .all()
    )
    return sorted(sessions, key=lambda s: as_utc(s.started_at))


def _confirmation_state(db: Session, candidate_profile_id: str) -> tuple[CandidateProfile | None, datetime | None]:
    """The profile and the moment a grade was first confirmed."""
    profile = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_profile_id).first()
    changes = db.query(GradeHistory.changed_at).filter(GradeHistory.candidate_profile_id == candidate_profile_id).all()
    first = min((as_utc(changed) for (changed,) in changes), default=None)
    if first is None and profile is not None and profile.confirmed_grade:
        first = datetime.min.replace(tzinfo=timezone.utc)  # grade set without a recorded confirmation (seed data)
    return profile, first


def _policy_status(db: Session, candidate_profile_id: str, sessions: list[AssessmentSession], now: datetime) -> GradeStatus:
    profile, first_confirmed = _confirmation_state(db, candidate_profile_id)
    return grade_status(
        [_record(s) for s in sessions],
        profile.confirmed_grade if profile else None,
        first_confirmed,
        profile.next_grade_change_available_at if profile else None,
        now,
        profile.confirmed_specialization if profile else None,
    )


def _follow_up_prior(db: Session, session: AssessmentSession) -> tuple[float, float] | None:
    """A follow-up test continues the previous measurement: its posterior becomes the prior."""
    if session.is_demo:
        return None
    sessions = _candidate_sessions(db, session.candidate_profile_id)
    idx = next(i for i, s in enumerate(sessions) if s.id == session.id)
    if idx and is_follow_up(_record(sessions[idx - 1]), _record(session)):
        return sessions[idx - 1].current_theta, sessions[idx - 1].current_se
    return None


def _item_limits(prior: tuple[float, float] | None, is_demo: bool = False) -> tuple[int, int]:
    if is_demo:
        return (DEMO_MIN_ITEMS, DEMO_MAX_ITEMS)
    return (FOLLOW_UP_MIN_ITEMS, FOLLOW_UP_MAX_ITEMS) if prior else (MIN_ITEMS, MAX_ITEMS)


def _session_topic_profile(db: Session, session: AssessmentSession) -> list[TopicProfileEntry]:
    answered = (
        db.query(SessionItem, ItemFamily)
        .join(ItemFamily, SessionItem.item_family_id == ItemFamily.id)
        .filter(SessionItem.session_id == session.id, SessionItem.is_correct.is_not(None))
        .all()
    )
    items = [(fam.topic, fam.discrimination_a, fam.difficulty_b, bool(si.is_correct)) for si, fam in answered]
    return [TopicProfileEntry(**entry) for entry in topic_profile(items, session.current_theta)]


def _regular_attempt(status_: GradeStatus) -> RegularAttempt:
    return RegularAttempt(
        allowed=status_.regular_allowed and status_.open_session_id is None,
        kind=status_.regular_kind,
        reason=status_.reason,
        message=status_.message,
        available_at=status_.available_at,
        initial_attempts_left=status_.initial_attempts_left,
    )


def _follow_up(status_: GradeStatus) -> FollowUpOffer | None:
    if not status_.follow_up_grade:
        return None
    return FollowUpOffer(grade=status_.follow_up_grade, specialization=status_.follow_up_specialization,
                         available_until=status_.follow_up_until)


JURY_PROFILE_ID = "jury-demo-candidate-profile"


def _jury_profile(db: Session) -> CandidateProfile:
    """The shared profile that owns every express session: hidden from employers, never graded."""
    jury_prof = db.query(CandidateProfile).filter(CandidateProfile.id == JURY_PROFILE_ID).first()
    if jury_prof:
        jury_prof.status = "HIDDEN"  # databases created before this rule kept it visible to employers
        return jury_prof
    jury_user = db.query(User).filter(User.email == "jury@fsp-talent.ru").first()
    if not jury_user:
        jury_user = User(
            id=str(uuid.uuid4()),
            email="jury@fsp-talent.ru",
            hashed_password=None,  # cannot sign in: the profile only owns express sessions
            role="CANDIDATE",
            is_active=True,
        )
        db.add(jury_user)
        db.flush()
    jury_prof = CandidateProfile(
        id=JURY_PROFILE_ID,
        user_id=jury_user.id,
        first_name="Эксперт",
        last_name="Жюри",
        status="HIDDEN",
    )
    db.add(jury_prof)
    db.flush()
    return jury_prof


def start_assessment_session(
    db: Session,
    req: AssessmentStartRequest,
) -> AssessmentStartResponse:
    """Initiate an adaptive CAT session."""
    sync_item_families_to_db(db)

    spec = req.specialization.upper().replace(" ", "_")
    grade = normalize_grade(req.target_grade)
    if grade not in GRADE_START_THETA:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown grade '{req.target_grade}'. Valid: {list(GRADE_START_THETA)}.",
        )
    has_bank = (
        db.query(ItemFamily.id)
        .filter(ItemFamily.is_active.is_(True), ItemFamily.specialization == spec)
        .first()
    )
    if not has_bank:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No item bank for specialization '{req.specialization}' yet.",
        )

    now = utcnow()
    is_demo_session = bool(req.is_demo or req.is_express)
    kind, prior = KIND_INITIAL, None
    cid = req.candidate_profile_id

    if is_demo_session:
        # The express test always runs on the jury profile, even inside a candidate's cabinet: it neither changes
        # the candidate's grade nor counts as their attempt, so it cannot serve as unlimited practice either.
        kind = "DEMO"
        cid = _jury_profile(db).id
    elif cid:
        sessions = _candidate_sessions(db, cid)
        for s in sessions:  # unfinished sessions past the time limit are abandoned and count as attempts
            if s.status == "IN_PROGRESS" and not _record(s).is_open(now):
                s.status = "ABANDONED"
        eligibility = check_eligibility(_policy_status(db, cid, sessions, now), grade, spec)
        if not eligibility.allowed:
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": eligibility.reason,
                    "message": eligibility.message,
                    "available_at": eligibility.available_at.isoformat() if eligibility.available_at else None,
                    "session_id": eligibility.open_session_id,
                },
            )
        kind = eligibility.kind
        if kind == KIND_FOLLOW_UP:
            prior = (sessions[-1].current_theta, sessions[-1].current_se)
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Квалификационный тест проходит авторизованный кандидат. Экспресс-тест доступен без входа.",
        )

    session = AssessmentSession(
        id=str(uuid.uuid4()),
        candidate_profile_id=cid,
        specialization=spec,
        target_grade=grade,
        # Selection starts at the centre of the declared grade (or where the previous test left off for a
        # follow-up); estimation keeps the N(0, 1) prior, or the previous posterior for a follow-up
        current_theta=prior[0] if prior else get_start_theta(grade),
        current_se=prior[1] if prior else 1.0,
        status="IN_PROGRESS",
        items_count=0,
        is_demo=is_demo_session,
        started_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    max_items = _item_limits(prior, is_demo=is_demo_session)[1]
    return AssessmentStartResponse(
        session_id=session.id,
        candidate_profile_id=session.candidate_profile_id,
        specialization=session.specialization,
        target_grade=session.target_grade,
        status=session.status,
        current_theta=session.current_theta,
        current_se=session.current_se,
        items_count=session.items_count,
        started_at=session.started_at,
        attempt_kind=kind,
        max_items=max_items,
        is_demo=session.is_demo,
    )


def get_next_item_for_session(
    db: Session,
    session_id: str,
) -> SessionNextItemResponse:
    """Retrieve or generate the next adaptive item for the session."""
    sync_item_families_to_db(db)

    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment session '{session_id}' not found.",
        )

    # 1. If session is already completed
    if session.status != "IN_PROGRESS":
        return SessionNextItemResponse(
            session_id=session.id,
            session_item_id="",
            family_code="",
            topic="",
            item_format="",
            seed=0,
            item_index=session.items_count,
            question_text="Тестирование завершено.",
            options={},
            is_finished=True,
            stopping_reason=f"SESSION_{session.status}",
        )

    # 2. Check if there is an uncompleted pending item already presented to candidate
    pending_item = (
        db.query(SessionItem)
        .filter(SessionItem.session_id == session.id, SessionItem.user_response.is_(None))
        .first()
    )
    if pending_item:
        item_family = db.query(ItemFamily).filter(ItemFamily.id == pending_item.item_family_id).first()
        render_res = render_family_item(item_family.code, pending_item.seed)
        return SessionNextItemResponse(
            session_id=session.id,
            session_item_id=pending_item.id,
            family_code=item_family.code,
            topic=item_family.topic,
            item_format=item_family.item_format,
            seed=pending_item.seed,
            item_index=session.items_count + 1,
            question_text=render_res.question_text,
            code_snippet=render_res.code_snippet,
            options=render_res.options,
            is_finished=False,
        )

    # 3. Check stopping criteria (a follow-up test is shorter; demo test is 5 items)
    is_demo_sess = bool(getattr(session, "is_demo", False))
    min_items, max_items = _item_limits(_follow_up_prior(db, session), is_demo=is_demo_sess)
    stop, reason = should_stop_assessment(
        items_count=session.items_count,
        current_se=session.current_se,
        min_items=min_items,
        max_items=max_items,
    )
    if stop:
        session.status = "COMPLETED"
        session.finished_at = utcnow()
        db.commit()
        return SessionNextItemResponse(
            session_id=session.id,
            session_item_id="",
            family_code="",
            topic="",
            item_format="",
            seed=0,
            item_index=session.items_count,
            question_text="Критерий завершения адаптивного тестирования достигнут.",
            options={},
            is_finished=True,
            stopping_reason=reason,
        )

    # 4. Prepare candidate item pool: this specialization only
    all_families = (
        db.query(ItemFamily)
        .filter(
            ItemFamily.is_active.is_(True),
            ItemFamily.specialization == session.specialization,
        )
        .all()
    )

    pool = [
        ItemCandidate(
            id=f.id,
            code=f.code,
            specialization=f.specialization,
            target_grade=f.target_grade,
            topic=f.topic,
            discrimination_a=f.discrimination_a,
            difficulty_b=f.difficulty_b,
            exposure_count=f.exposure_count,
            is_active=f.is_active,
        )
        for f in all_families
    ]

    # Gather already administered items in this session
    administered_items = (
        db.query(SessionItem)
        .filter(SessionItem.session_id == session.id)
        .all()
    )
    administered_ids = {it.item_family_id for it in administered_items}
    # Families from the candidate's earlier sessions are avoided while unseen ones remain
    history_ids: set[str] = set()
    if session.candidate_profile_id:
        past_items = (
            db.query(SessionItem.item_family_id)
            .join(AssessmentSession, SessionItem.session_id == AssessmentSession.id)
            .filter(
                AssessmentSession.candidate_profile_id == session.candidate_profile_id,
                AssessmentSession.id != session.id,
            )
            .all()
        )
        history_ids.update(fid for (fid,) in past_items)

    # Gather administered topics
    family_map = {f.id: f for f in all_families}
    administered_topics = [
        family_map[it.item_family_id].topic
        for it in administered_items
        if it.item_family_id in family_map
    ]

    spec_sessions = (
        db.query(AssessmentSession)
        .filter(AssessmentSession.specialization == session.specialization)
        .count()
    )

    # 5. Adaptive item selection (Randomesque Top-5 Maximum Fisher Information)
    selected_candidate = select_next_item(
        pool=pool,
        current_theta=session.current_theta,
        administered_item_ids=administered_ids,
        administered_topics=administered_topics,
        specialization=session.specialization,
        history_item_ids=history_ids,
        spec_session_count=spec_sessions,
    )

    if not selected_candidate:
        # Bank exhausted -> finish session
        session.status = "COMPLETED"
        session.finished_at = utcnow()
        db.commit()
        return SessionNextItemResponse(
            session_id=session.id,
            session_item_id="",
            family_code="",
            topic="",
            item_format="",
            seed=0,
            item_index=session.items_count,
            question_text="Банк заданий исчерпан. Тестирование завершено.",
            options={},
            is_finished=True,
            stopping_reason="ITEM_BANK_EXHAUSTED",
        )

    # 6. Render instance with unique random seed
    seed = random.randint(1, 1_000_000)
    render_res = render_family_item(selected_candidate.code, seed)

    # 7. Persist SessionItem in DB
    session_item = SessionItem(
        id=str(uuid.uuid4()),
        session_id=session.id,
        item_family_id=selected_candidate.id,
        seed=seed,
        rendered_question=json.dumps(render_res.to_client_dict(), ensure_ascii=False),
        presented_at=utcnow(),
    )
    db.add(session_item)

    # Increment item exposure
    db_family = db.query(ItemFamily).filter(ItemFamily.id == selected_candidate.id).first()
    if db_family:
        db_family.exposure_count += 1

    db.commit()
    db.refresh(session_item)

    return SessionNextItemResponse(
        session_id=session.id,
        session_item_id=session_item.id,
        family_code=selected_candidate.code,
        topic=selected_candidate.topic,
        item_format=family_map[selected_candidate.id].item_format,
        seed=seed,
        item_index=session.items_count + 1,
        question_text=render_res.question_text,
        code_snippet=render_res.code_snippet,
        options=render_res.options,
        is_finished=False,
    )


def record_candidate_answer(
    db: Session,
    session_id: str,
    req: AssessmentAnswerRequest,
) -> AssessmentAnswerResponse:
    """Check correctness of submitted answer, update theta/SE, and check stopping rules."""
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment session '{session_id}' not found.",
        )

    if session.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Assessment session is already in '{session.status}' state.",
        )

    # Find pending item
    query = db.query(SessionItem).filter(
        SessionItem.session_id == session.id,
        SessionItem.user_response.is_(None),
    )
    if req.session_item_id:
        pending_item = query.filter(SessionItem.id == req.session_item_id).first()
    else:
        pending_item = query.first()

    if not pending_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No unanswered question pending for this session.",
        )

    item_family = db.query(ItemFamily).filter(ItemFamily.id == pending_item.item_family_id).first()
    render_res = render_family_item(item_family.code, pending_item.seed)

    user_resp_clean = req.response.strip().upper()
    correct_resp_clean = render_res.correct_answer.strip().upper()
    is_correct = (user_resp_clean == correct_resp_clean)

    # Record item response
    pending_item.user_response = req.response.strip()
    pending_item.is_correct = is_correct
    pending_item.response_time_seconds = req.response_time_seconds
    pending_item.answered_at = utcnow()

    session.items_count += 1

    # Fetch all answered items for EAP theta re-estimation
    answered_items = (
        db.query(SessionItem, ItemFamily)
        .join(ItemFamily, SessionItem.item_family_id == ItemFamily.id)
        .filter(
            SessionItem.session_id == session.id,
            SessionItem.is_correct.is_not(None),
        )
        .all()
    )

    responses = [1 if si.is_correct else 0 for si, fam in answered_items]
    item_params = [(fam.discrimination_a, fam.difficulty_b) for si, fam in answered_items]

    prior = _follow_up_prior(db, session)
    if prior:
        new_theta, new_se = estimate_theta_eap(responses, item_params, prior_mean=prior[0], prior_sd=max(prior[1], 0.1))
    else:
        new_theta, new_se = estimate_theta_eap(responses, item_params)
    session.current_theta = new_theta
    session.current_se = new_se

    # Check stopping rules
    is_demo_sess = bool(getattr(session, "is_demo", False))
    min_items, max_items = _item_limits(prior, is_demo=is_demo_sess)
    stop, reason = should_stop_assessment(session.items_count, session.current_se, min_items=min_items, max_items=max_items)
    if stop:
        session.status = "COMPLETED"
        session.finished_at = utcnow()

    db.commit()
    db.refresh(session)

    return AssessmentAnswerResponse(
        session_id=session.id,
        is_correct=is_correct,
        current_theta=session.current_theta,
        current_se=session.current_se,
        items_count=session.items_count,
        is_finished=(session.status == "COMPLETED"),
        stopping_reason=reason if stop else None,
    )


def finish_assessment_session(
    db: Session,
    session_id: str,
) -> AssessmentFinishResponse:
    """Grade a completed session and apply the attempt policy to the candidate profile.

    Idempotent: the result is applied once (tracked by GradeHistory.assessment_session_id), so a repeated
    call returns the same outcome. A failed attempt never lowers the confirmed grade or its percentile.
    """
    session = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment session '{session_id}' not found.",
        )

    # A session is graded only after the stopping rule (or bank exhaustion) closed it;
    # otherwise an abandoned session would be graded on its starting point.
    if session.status != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment is not finished yet: keep answering until the session reports is_finished.",
        )
    now = utcnow()
    evaluation = evaluate_assessment_result(
        target_grade=session.target_grade,
        theta=session.current_theta,
        se=session.current_se,
        now=as_utc(session.finished_at) or now,
    )
    percentile = calculate_category_percentile(session.current_theta)
    category = format_category(session.specialization, evaluation.confirmed_grade) if evaluation.is_confirmed else None

    cid = session.candidate_profile_id
    sessions = _candidate_sessions(db, cid)
    is_demo = bool(getattr(session, "is_demo", False))
    if is_demo:
        kind = "DEMO"
    else:
        kind = _policy_status(db, cid, sessions, now).attempt_kinds[[s.id for s in sessions].index(session.id)]

    profile = db.query(CandidateProfile).filter(CandidateProfile.id == cid).first()
    already_applied = (
        db.query(GradeHistory.id).filter(GradeHistory.assessment_session_id == session.id).first() is not None
    )
    if profile is not None and not already_applied:
        if is_demo:
            # Demo sessions do not alter permanent profile grades or impose retake cooldowns
            pass
        elif evaluation.is_confirmed:
            previous_grade = profile.confirmed_grade
            profile.confirmed_grade = evaluation.confirmed_grade
            profile.declared_grade = evaluation.confirmed_grade
            profile.confirmed_specialization = session.specialization
            profile.confirmed_category = category
            profile.last_theta = session.current_theta
            profile.last_se = session.current_se
            profile.category_percentile = percentile
            profile.next_grade_change_available_at = evaluation.next_grade_change_available_at
            db.add(GradeHistory(
                id=str(uuid.uuid4()),
                candidate_profile_id=profile.id,
                previous_grade=previous_grade,
                new_grade=evaluation.confirmed_grade,
                specialization=session.specialization,
                reason=f"ASSESSMENT_{kind}",
                assessment_session_id=session.id,
                changed_at=now,
            ))
        else:
            if not profile.confirmed_grade:
                # nothing confirmed yet: track declared grade and measurement
                profile.declared_grade = session.target_grade
                if not profile.confirmed_specialization:
                    profile.confirmed_specialization = session.specialization
                profile.last_theta = session.current_theta
                profile.last_se = session.current_se
                profile.category_percentile = percentile
            if kind == KIND_CHANGE:
                # a failed change attempt uses up the 90-day slot but keeps the grade and its percentile
                profile.next_grade_change_available_at = (
                    as_utc(session.started_at) + timedelta(days=GRADE_CHANGE_COOLDOWN_DAYS)
                )
    db.commit()

    after = _policy_status(db, cid, sessions, now) if not is_demo else None
    explanation = (
        f"[Экспресс-тест для жюри] {evaluation.explanation}"
        if is_demo
        else evaluation.explanation
    )
    return AssessmentFinishResponse(
        session_id=session.id,
        status=session.status,
        final_theta=session.current_theta,
        final_se=session.current_se,
        items_count=session.items_count,
        target_grade=session.target_grade,
        is_confirmed=evaluation.is_confirmed,
        confirmed_grade=evaluation.confirmed_grade,
        confirmed_category=category,
        category_percentile=percentile,
        recommendation=evaluation.recommendation,
        suggested_grade=evaluation.suggested_grade,
        explanation=explanation,
        next_grade_change_available_at=(
            None if is_demo else (as_utc(profile.next_grade_change_available_at) if profile else evaluation.next_grade_change_available_at)
        ),
        attempt_kind=kind,
        grade_applied=evaluation.is_confirmed and profile is not None and not is_demo,
        is_demo=is_demo,
        follow_up=_follow_up(after) if after else None,
        regular_attempt=_regular_attempt(after) if after else RegularAttempt(
            allowed=True,
            kind="DEMO",
            reason="ALLOWED",
            message="Экспресс-тест для жюри: доступен повторный запуск без ограничений.",
        ),
        topic_profile=_session_topic_profile(db, session),
    )


def get_grade_status(db: Session, candidate_profile_id: str) -> GradeStatusResponse:
    """Status, attempt history and grade changes of a candidate (the "категория и грейд" screen)."""
    now = utcnow()
    sessions = _candidate_sessions(db, candidate_profile_id)
    profile, _ = _confirmation_state(db, candidate_profile_id)
    if profile is None and not sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate profile '{candidate_profile_id}' not found.",
        )
    status_ = _policy_status(db, candidate_profile_id, sessions, now)

    attempts = []
    for s, kind in zip(sessions, status_.attempt_kinds):
        record = _record(s)
        evaluation = record.evaluation()
        shown_status = "ABANDONED" if s.status == "IN_PROGRESS" and not record.is_open(now) else s.status
        attempts.append(AttemptSummary(
            session_id=s.id,
            specialization=s.specialization,
            target_grade=s.target_grade,
            status=shown_status,
            kind=kind,
            started_at=as_utc(s.started_at),
            finished_at=as_utc(s.finished_at),
            items_count=s.items_count,
            theta=s.current_theta if evaluation else None,
            se=s.current_se if evaluation else None,
            is_confirmed=evaluation.is_confirmed if evaluation else None,
            recommendation=evaluation.recommendation if evaluation else None,
        ))

    changes = (
        db.query(GradeHistory)
        .filter(GradeHistory.candidate_profile_id == candidate_profile_id)
        .all()
    )
    changes.sort(key=lambda h: as_utc(h.changed_at))
    # topics of the session that set the current grade, else of the latest completed session
    by_id = {s.id: s for s in sessions}
    source = by_id.get(changes[-1].assessment_session_id) if changes else None
    if source is None:
        source = next((s for s in reversed(sessions) if s.status == "COMPLETED"), None)

    return GradeStatusResponse(
        candidate_profile_id=candidate_profile_id,
        confirmed_specialization=profile.confirmed_specialization if profile else None,
        confirmed_grade=profile.confirmed_grade if profile else None,
        confirmed_category=profile.confirmed_category if profile else None,
        category_percentile=profile.category_percentile if profile and profile.confirmed_grade else None,
        theta=profile.last_theta if profile and profile.confirmed_grade else None,
        se=profile.last_se if profile and profile.confirmed_grade else None,
        next_grade_change_available_at=as_utc(profile.next_grade_change_available_at) if profile else None,
        open_session_id=status_.open_session_id,
        regular_attempt=_regular_attempt(status_),
        follow_up=_follow_up(status_),
        topic_profile=_session_topic_profile(db, source) if source else [],
        attempts=attempts,
        grade_history=[
            GradeChangeEntry(previous_grade=h.previous_grade, new_grade=h.new_grade, specialization=h.specialization,
                             reason=h.reason, changed_at=as_utc(h.changed_at))
            for h in changes
        ],
    )
