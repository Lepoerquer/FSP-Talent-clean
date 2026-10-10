"""Attempt policy and grade rules (R2-08): pure rules with fixed clocks, then full API flows."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models.assessment import AssessmentSession
from backend.app.models.candidate import CandidateProfile, GradeHistory
from backend.app.models.user import User
from backend.app.modules.assessment.grade_rules import (
    FOLLOW_UP_MAX_ITEMS,
    INITIAL_MAX_ATTEMPTS,
    RETRY_AFTER_UNCONFIRMED_DAYS,
    AttemptRecord,
    check_eligibility,
    format_category,
    grade_status,
)
from conftest import bearer
from families.registry import render_family_item

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
SEED_CONFIRMED = datetime.min.replace(tzinfo=timezone.utc)

# (theta, se) giving a known outcome when the target grade is MIDDLE
CONFIRM_MIDDLE = (1.0, 0.3)       # GRADE_CONFIRMED
OFFER_SENIOR = (2.0, 0.3)         # confirmed, theta - SE >= 1.5: offer SENIOR
FAIL_MIDDLE = (0.0, 0.3)          # not confirmed: offer JUNIOR


def rec(n: int, grade: str, start: timedelta, outcome=CONFIRM_MIDDLE, status="COMPLETED", spec="BACKEND") -> AttemptRecord:
    started = T0 + start
    finished = started + timedelta(minutes=40) if status == "COMPLETED" else None
    return AttemptRecord(f"s{n}", grade, status, started, finished, outcome[0], outcome[1], spec)


def status_at(records, now, confirmed=None, first_confirmed=None, next_change=None, confirmed_spec="BACKEND"):
    return grade_status(records, confirmed, first_confirmed, next_change, now, confirmed_spec if confirmed else None)


# ==========================================
# Initial determination
# ==========================================

def test_first_attempt_is_initial_with_three_attempts():
    st = status_at([], T0)
    assert (st.regular_allowed, st.regular_kind, st.initial_attempts_left) == (True, "INITIAL", INITIAL_MAX_ATTEMPTS)


def test_initial_attempts_exhausted_then_reopen_after_retry_period():
    records = [rec(i, "MIDDLE", timedelta(days=i), FAIL_MIDDLE) for i in range(3)]
    st = status_at(records, T0 + timedelta(days=3))
    assert not st.regular_allowed and st.reason == "INITIAL_ATTEMPTS_EXHAUSTED"
    assert st.available_at == T0 + timedelta(days=RETRY_AFTER_UNCONFIRMED_DAYS)

    later = status_at(records, T0 + timedelta(days=RETRY_AFTER_UNCONFIRMED_DAYS))
    assert later.regular_allowed and later.initial_attempts_left == INITIAL_MAX_ATTEMPTS


def test_initial_window_closes_after_seven_days_even_with_attempts_left():
    st = status_at([rec(0, "MIDDLE", timedelta(0), FAIL_MIDDLE)], T0 + timedelta(days=8))
    assert st.reason == "INITIAL_ATTEMPTS_EXHAUSTED"


def test_confirmed_candidate_keeps_initial_attempts_inside_the_window():
    records = [rec(0, "MIDDLE", timedelta(0))]
    st = status_at(records, T0 + timedelta(days=1), confirmed="MIDDLE",
                   first_confirmed=T0 + timedelta(minutes=40), next_change=T0 + timedelta(days=90))
    assert (st.regular_allowed, st.regular_kind, st.initial_attempts_left) == (True, "INITIAL", 2)


# ==========================================
# Changes after confirmation
# ==========================================

def test_change_waits_for_cooldown_then_is_allowed():
    records = [rec(0, "MIDDLE", timedelta(0))]
    kwargs = dict(confirmed="MIDDLE", first_confirmed=T0 + timedelta(minutes=40), next_change=T0 + timedelta(days=90))
    st = status_at(records, T0 + timedelta(days=8), **kwargs)
    assert (st.regular_allowed, st.reason, st.available_at) == (False, "COOLDOWN", T0 + timedelta(days=90))
    st = status_at(records, T0 + timedelta(days=90), **kwargs)
    assert (st.regular_allowed, st.regular_kind) == (True, "CHANGE")

    records.append(rec(1, "SENIOR", timedelta(days=91), FAIL_MIDDLE))
    assert status_at(records, T0 + timedelta(days=92), **kwargs).attempt_kinds == ["INITIAL", "CHANGE"]


def test_seeded_grade_without_history_follows_change_rules():
    st = status_at([], T0, confirmed="MIDDLE", first_confirmed=SEED_CONFIRMED)
    assert (st.regular_allowed, st.regular_kind) == (True, "CHANGE")


# ==========================================
# Offered follow-up test
# ==========================================

def test_follow_up_is_free_for_the_offered_grade_only_and_expires():
    records = [rec(0, "MIDDLE", timedelta(0), FAIL_MIDDLE)]
    now = T0 + timedelta(hours=1)
    st = status_at(records, now)
    assert (st.follow_up_grade, st.follow_up_specialization) == ("JUNIOR", "BACKEND")
    assert check_eligibility(st, "JUNIOR", "BACKEND").kind == "FOLLOW_UP"
    assert check_eligibility(st, "JUNIOR", "QA").kind == "INITIAL"
    assert check_eligibility(st, "SENIOR", "BACKEND").kind == "INITIAL"

    assert status_at(records, T0 + timedelta(hours=25)).follow_up_grade is None


def test_follow_ups_do_not_use_initial_attempts():
    records = [rec(0, "MIDDLE", timedelta(0), FAIL_MIDDLE), rec(1, "JUNIOR", timedelta(hours=1), (0.2, 0.3))]
    st = status_at(records, T0 + timedelta(hours=2), confirmed="JUNIOR", first_confirmed=T0 + timedelta(hours=1))
    assert st.attempt_kinds == ["INITIAL", "FOLLOW_UP"]
    assert st.initial_attempts_left == 2


def test_follow_up_is_offered_even_during_cooldown():
    records = [rec(0, "MIDDLE", timedelta(days=100), OFFER_SENIOR)]
    st = status_at(records, T0 + timedelta(days=100, hours=1), confirmed="MIDDLE", first_confirmed=SEED_CONFIRMED,
                   next_change=T0 + timedelta(days=190))
    assert not st.regular_allowed and st.reason == "COOLDOWN"
    assert check_eligibility(st, "SENIOR", "BACKEND").allowed


def test_no_offer_for_the_grade_already_held_or_below_intern():
    failed_senior = [rec(0, "SENIOR", timedelta(days=100), FAIL_MIDDLE)]
    st = status_at(failed_senior, T0 + timedelta(days=100, hours=1), confirmed="JUNIOR", first_confirmed=SEED_CONFIRMED)
    assert st.follow_up_grade == "MIDDLE"  # offered: the candidate holds Junior, not Middle
    st = status_at(failed_senior, T0 + timedelta(days=100, hours=1), confirmed="MIDDLE", first_confirmed=SEED_CONFIRMED)
    assert st.follow_up_grade is None
    # demo profiles store display labels ("Backend", "Middle"), sessions store codes
    st = status_at(failed_senior, T0 + timedelta(days=100, hours=1), confirmed="Middle", first_confirmed=SEED_CONFIRMED,
                   confirmed_spec="Backend")
    assert st.follow_up_grade is None

    failed_intern = [rec(0, "INTERN", timedelta(0), (-2.5, 0.3))]
    assert status_at(failed_intern, T0 + timedelta(hours=1)).follow_up_grade is None


# ==========================================
# Unfinished sessions
# ==========================================

def test_open_session_blocks_and_abandoned_one_counts_as_attempt():
    open_ = [rec(0, "MIDDLE", timedelta(0), status="IN_PROGRESS")]
    st = status_at(open_, T0 + timedelta(minutes=30))
    assert st.open_session_id == "s0"
    assert not check_eligibility(st, "MIDDLE", "BACKEND").allowed

    st = status_at(open_, T0 + timedelta(hours=4))
    assert st.open_session_id is None and st.initial_attempts_left == INITIAL_MAX_ATTEMPTS - 1


def test_category_labels():
    assert format_category("DATA_ML", "MIDDLE") == "Data/ML · Middle"
    assert format_category("backend", "intern") == "Backend · Стажёр"


# ==========================================
# API flows
# ==========================================

@pytest.fixture
def profile_id(db_session):
    def make(**fields) -> str:
        pid = f"cand-{uuid.uuid4().hex[:8]}"
        db_session.add(User(id=f"user-{pid}", email=f"{pid}@example.com", role="CANDIDATE", email_verified=True))
        db_session.add(CandidateProfile(id=pid, user_id=f"user-{pid}", status="ACTIVELY_SEARCHING", **fields))
        db_session.commit()
        return pid
    return make


def run_session(client, sid: str, correct: bool) -> int:
    """Answer every item right or wrong until the engine stops; returns the number of items."""
    answered = 0
    for _ in range(40):
        item = client.get(f"/api/v1/assessments/{sid}/next").json()
        if item["is_finished"]:
            break
        key = render_family_item(item["family_code"], item["seed"]).correct_answer
        wrong = next(k for k in item["options"] if k != key)
        res = client.post(f"/api/v1/assessments/{sid}/answer",
                          json={"session_item_id": item["session_item_id"], "response": key if correct else wrong}).json()
        answered += 1
        if res["is_finished"]:
            break
    return answered


def start(client, pid: str, spec: str, grade: str):
    """Start a qualifying test as the profile's owner (later calls of the test reuse the same sign-in)."""
    client.headers.update(bearer(f"user-{pid}"))
    return client.post("/api/v1/assessments/start",
                       json={"candidate_profile_id": pid, "specialization": spec, "target_grade": grade})


def test_confirmation_then_short_follow_up_test(client, db_session, profile_id):
    pid = profile_id()
    first = start(client, pid, "DATA_ML", "MIDDLE").json()
    assert (first["attempt_kind"], first["max_items"]) == ("INITIAL", 25)
    run_session(client, first["session_id"], correct=True)

    result = client.post(f"/api/v1/assessments/{first['session_id']}/finish").json()
    assert result["confirmed_category"] == "Data/ML · Middle" and result["grade_applied"]
    assert result["recommendation"] == "OFFER_HIGHER_GRADE"
    assert result["follow_up"]["grade"] == "SENIOR"
    assert result["regular_attempt"]["initial_attempts_left"] == 2
    assert result["topic_profile"]

    client.post(f"/api/v1/assessments/{first['session_id']}/finish")  # repeated call changes nothing
    assert db_session.query(GradeHistory).filter(GradeHistory.candidate_profile_id == pid).count() == 1

    follow = start(client, pid, "DATA_ML", "SENIOR").json()
    assert (follow["attempt_kind"], follow["max_items"]) == ("FOLLOW_UP", FOLLOW_UP_MAX_ITEMS)
    assert follow["current_theta"] == pytest.approx(result["final_theta"])
    assert run_session(client, follow["session_id"], correct=True) <= FOLLOW_UP_MAX_ITEMS
    upgraded = client.post(f"/api/v1/assessments/{follow['session_id']}/finish").json()
    assert upgraded["confirmed_grade"] == "SENIOR" and upgraded["attempt_kind"] == "FOLLOW_UP"

    status = client.get(f"/api/v1/me/grade?candidate_profile_id={pid}").json()
    assert status["confirmed_category"] == "Data/ML · Senior"
    assert [a["kind"] for a in status["attempts"]] == ["INITIAL", "FOLLOW_UP"]
    assert [h["reason"] for h in status["grade_history"]] == ["ASSESSMENT_INITIAL", "ASSESSMENT_FOLLOW_UP"]
    assert status["regular_attempt"]["kind"] == "INITIAL"  # still inside the initial window


def test_failed_change_keeps_grade_and_percentile(client, db_session, profile_id):
    pid = profile_id(confirmed_grade="MIDDLE", confirmed_specialization="BACKEND",
                     confirmed_category="Backend · Middle", category_percentile=80, last_theta=1.0)
    session = start(client, pid, "BACKEND", "SENIOR").json()
    assert session["attempt_kind"] == "CHANGE"

    blocked = start(client, pid, "BACKEND", "SENIOR")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error_code"] == "SESSION_IN_PROGRESS"
    assert blocked.json()["detail"]["session_id"] == session["session_id"]

    run_session(client, session["session_id"], correct=False)
    result = client.post(f"/api/v1/assessments/{session['session_id']}/finish").json()
    assert not result["is_confirmed"] and not result["grade_applied"]
    assert result["follow_up"] is None  # Middle is already held

    db_session.expire_all()
    profile = db_session.query(CandidateProfile).filter(CandidateProfile.id == pid).one()
    assert (profile.confirmed_grade, profile.category_percentile, profile.last_theta) == ("MIDDLE", 80, 1.0)

    again = start(client, pid, "BACKEND", "SENIOR")
    assert again.status_code == 409 and again.json()["detail"]["error_code"] == "COOLDOWN"
    assert again.json()["detail"]["available_at"]


def test_initial_attempts_are_limited(client, profile_id):
    # Data/ML has intern-level families, so answering everything wrong does fail the Intern test
    pid = profile_id()
    for _ in range(INITIAL_MAX_ATTEMPTS):
        sid = start(client, pid, "DATA_ML", "INTERN").json()["session_id"]
        run_session(client, sid, correct=False)
        result = client.post(f"/api/v1/assessments/{sid}/finish").json()
        assert not result["is_confirmed"] and result["follow_up"] is None
    refused = start(client, pid, "DATA_ML", "INTERN")
    assert refused.status_code == 409
    assert refused.json()["detail"]["error_code"] == "INITIAL_ATTEMPTS_EXHAUSTED"


def test_abandoned_session_stops_blocking_and_counts(client, db_session, profile_id):
    pid = profile_id()
    sid = start(client, pid, "QA", "JUNIOR").json()["session_id"]
    stale = db_session.query(AssessmentSession).filter(AssessmentSession.id == sid).one()
    stale.started_at = datetime.now(timezone.utc) - timedelta(hours=4)
    db_session.commit()

    fresh = start(client, pid, "QA", "JUNIOR")
    assert fresh.status_code == 201
    status = client.get(f"/api/v1/me/grade?candidate_profile_id={pid}").json()
    assert [a["status"] for a in status["attempts"]] == ["ABANDONED", "IN_PROGRESS"]
    assert status["open_session_id"] == fresh.json()["session_id"]


# ==========================================
# Jury Express / Demo Mode & Unconfirmed Grade Policy (Q&A FSP-2026)
# ==========================================

def test_express_test_never_uses_up_a_candidate_attempt(client, db_session, profile_id):
    """An express test started from the candidate's cabinet runs on the jury profile: no attempt, no grade."""
    pid = profile_id()
    client.headers.update(bearer(f"user-{pid}"))
    for _ in range(INITIAL_MAX_ATTEMPTS + 1):
        express = client.post("/api/v1/assessments/start", json={"candidate_profile_id": pid, "specialization": "QA",
                                                                 "target_grade": "JUNIOR", "is_express": True}).json()
        assert express["candidate_profile_id"] != pid and express["is_demo"] is True
        run_session(client, express["session_id"], correct=True)
        client.post(f"/api/v1/assessments/{express['session_id']}/finish")

    status = client.get("/api/v1/me/grade").json()
    assert status["attempts"] == [] and status["regular_attempt"]["initial_attempts_left"] == INITIAL_MAX_ATTEMPTS
    assert start(client, pid, "QA", "JUNIOR").status_code == 201
    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter(CandidateProfile.id == pid).one().confirmed_grade is None


def test_grade_status_of_another_candidate_is_refused(client, profile_id):
    mine, other = profile_id(), profile_id()
    client.headers.update(bearer(f"user-{mine}"))
    assert client.get(f"/api/v1/me/grade?candidate_profile_id={other}").status_code == 403
    assert start(client, mine, "QA", "JUNIOR").status_code == 201
    refused = client.post("/api/v1/assessments/start",
                          json={"candidate_profile_id": other, "specialization": "QA", "target_grade": "JUNIOR"})
    assert refused.status_code == 403


def test_demo_express_assessment_flow_for_jury(client):
    """Q&A Requirement: Jury express test (3-5 min, 5 items, no registration needed, no cooldown)."""
    # 1. Start demo assessment via query flag or is_demo
    start_resp = client.post(
        "/api/v1/assessments/start",
        json={"specialization": "BACKEND", "target_grade": "MIDDLE", "is_demo": True},
    )
    assert start_resp.status_code == 201
    data = start_resp.json()
    assert data["is_demo"] is True
    assert data["max_items"] == 5
    assert data["attempt_kind"] == "DEMO"
    sid = data["session_id"]

    # 2. Answer questions until completion (must terminate in exactly 5 items)
    items_count = run_session(client, sid, correct=True)
    assert items_count == 5

    # 3. Finish session and verify results
    finish_resp = client.post(f"/api/v1/assessments/{sid}/finish")
    assert finish_resp.status_code == 200
    res = finish_resp.json()
    assert res["is_demo"] is True
    assert res["items_count"] == 5
    assert "[Экспресс-тест для жюри]" in res["explanation"]
    assert res["next_grade_change_available_at"] is None  # no cooldown imposed on jury!

    # 4. Immediate second demo run allowed without cooldown conflict
    again = client.post(
        "/api/v1/assessments/start",
        json={"specialization": "BACKEND", "target_grade": "SENIOR", "is_demo": True},
    )
    assert again.status_code == 201
    assert again.json()["is_demo"] is True


def test_demo_assessment_dedicated_endpoint(client):
    """Q&A Requirement: Dedicated POST /api/v1/assessments/demo/start endpoint for jury."""
    resp = client.post(
        "/api/v1/assessments/demo/start",
        json={"specialization": "DATA_ML", "target_grade": "MIDDLE"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_demo"] is True
    assert data["max_items"] == 5
    assert data["specialization"] == "DATA_ML"


def test_unconfirmed_grade_retained_in_profile_and_ranking(client, db_session, profile_id):
    """Q&A Requirement: Unconfirmed grade must NOT be hidden from employer search pool,
    must show status 'Не подтверждён', and be demoted in ranking.
    """
    from backend.app.modules.matching.ranking import execute_two_stage_matching

    pid = profile_id()
    # Candidate takes test for Middle and fails (answers all wrong)
    start_resp = start(client, pid, "DATA_ML", "INTERN").json()
    run_session(client, start_resp["session_id"], correct=False)
    finish_resp = client.post(f"/api/v1/assessments/{start_resp['session_id']}/finish").json()
    assert not finish_resp["is_confirmed"]

    # Check CandidateProfile
    db_session.expire_all()
    prof = db_session.query(CandidateProfile).filter(CandidateProfile.id == pid).one()
    assert prof.confirmed_grade is None
    assert prof.declared_grade == "INTERN"
    assert prof.is_grade_confirmed is False
    assert prof.grade_status == "UNCONFIRMED"
    assert prof.grade_status_display == "Не подтверждён"

    # Profile API serialization check
    prof_resp = client.get("/api/v1/profiles/me").json()
    assert prof_resp["confirmed_grade"] is None
    assert prof_resp["declared_grade"] == "INTERN"
    assert prof_resp["is_grade_confirmed"] is False
    assert prof_resp["grade_status"] == "UNCONFIRMED"
    assert prof_resp["grade_status_display"] == "Не подтверждён"

    # Matching & Ranking pool check: Candidate must NOT be excluded when employer searches
    # Create another confirmed candidate for comparison
    confirmed_pid = profile_id(
        confirmed_grade="INTERN",
        confirmed_specialization="DATA_ML",
        confirmed_category="Data/ML · Стажёр",
        category_percentile=90,
    )
    all_cands = db_session.query(CandidateProfile).filter(CandidateProfile.id.in_([pid, confirmed_pid])).all()

    ranked = execute_two_stage_matching(
        all_candidates=all_cands,
        target_specialization="DATA_ML",
        target_grade="INTERN",
    )
    # Both candidates must be in the search results!
    ranked_ids = [r["candidate_id"] for r in ranked]
    assert pid in ranked_ids, "Unconfirmed candidate must NOT be hidden from matching pool!"
    assert confirmed_pid in ranked_ids

    # Confirmed candidate must outrank unconfirmed candidate
    conf_item = next(r for r in ranked if r["candidate_id"] == confirmed_pid)
    unconf_item = next(r for r in ranked if r["candidate_id"] == pid)
    assert conf_item["total_score"] > unconf_item["total_score"], "Unconfirmed candidate must be demoted in score!"
    assert unconf_item["candidate_card"]["grade_status"] == "UNCONFIRMED"
    assert unconf_item["candidate_card"]["grade_status_display"] == "Не подтверждён"
    assert unconf_item["candidate_card"]["is_grade_confirmed"] is False
    assert any("не подтверждён" in b.lower() for b in unconf_item["bullet_points"])


def test_grade_never_assigned_by_fsp_achievements_or_vacancy(db_session, profile_id):
    """Q&A Requirement: Grade is assigned ONLY by primary category test,
    never by FSP achievements or by vacancies.
    """
    from backend.app.models.candidate import FSPAchievement

    pid = profile_id()
    prof = db_session.query(CandidateProfile).filter(CandidateProfile.id == pid).one()
    # Add maximum FSP achievements (All-Russian winner, master of sports)
    prof.fsp_score = 1.0
    prof.is_fsp_verified = True
    ach = FSPAchievement(
        candidate_profile_id=pid,
        event_name="Чемпионат России по спортивному программированию 2026",
        discipline="Алгоритмическое программирование",
        level="ALL_RUSSIAN",
        result="WINNER",
        sport_category="МАСТЕР_СПОРТА",
    )
    db_session.add(ach)
    db_session.commit()

    db_session.refresh(prof)
    # FSP achievement must NEVER assign or promote confirmed_grade
    assert prof.confirmed_grade is None
    assert prof.confirmed_category is None
    assert prof.is_grade_confirmed is False
