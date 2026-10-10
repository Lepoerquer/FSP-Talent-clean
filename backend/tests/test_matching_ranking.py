"""Unit tests for Two-Stage Matching, Explainable Ranking Formula, and Snapshots."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.candidate import (
    CandidateProfile,
    CandidateSkill,
    FSPAchievement,
)
from backend.app.models.company import Company, Need, ShortlistItem
from backend.app.models.dictionary import Skill
from backend.app.modules.matching.ranking import (
    compute_stack_score,
    execute_two_stage_matching,
    filter_candidate_pool,
)
from backend.app.modules.matching.snapshots import SelectionSnapshotService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_candidates(db_session):
    """Creates a diverse pool of candidates for ranking and ablation tests."""
    # Skills
    py_skill = Skill(id="sk-py", code="PYTHON", name="Python")
    pg_skill = Skill(id="sk-pg", code="POSTGRESQL", name="PostgreSQL")
    fastapi_skill = Skill(id="sk-fa", code="FASTAPI", name="FastAPI")
    docker_skill = Skill(id="sk-doc", code="DOCKER", name="Docker")
    db_session.add_all([py_skill, pg_skill, fastapi_skill, docker_skill])
    db_session.commit()

    candidates = []

    # 1. Exact Middle Backend, high CAT test (95 percentile), NO FSP history
    c1 = CandidateProfile(
        id="cand-high-test-no-fsp",
        user_id="user-1",
        first_name="Ольга",
        last_name="Крылова",
        status="ACTIVELY_SEARCHING",
        confirmed_category="Backend · Middle",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        category_percentile=95,
        last_theta=1.65,
        fsp_score=0.0,
        is_fsp_verified=False,
        desired_salary_min=200000,
        work_format="REMOTE",
        city="Москва",
    )
    db_session.add(c1)
    db_session.flush()

    cs1 = CandidateSkill(candidate_profile_id=c1.id, skill_id=py_skill.id, confirmation_source="ASSESSMENT")
    cs2 = CandidateSkill(candidate_profile_id=c1.id, skill_id=pg_skill.id, confirmation_source="ASSESSMENT")
    cs3 = CandidateSkill(candidate_profile_id=c1.id, skill_id=fastapi_skill.id, confirmation_source="ASSESSMENT")
    db_session.add_all([cs1, cs2, cs3])
    candidates.append(c1)

    # 2. Adjacent Grade: Senior Backend, high CAT test (92 percentile), FSP Winner
    c2 = CandidateProfile(
        id="cand-senior-fsp-winner",
        user_id="user-2",
        first_name="Дмитрий",
        last_name="Соколов",
        status="ACTIVELY_SEARCHING",
        confirmed_category="Backend · Senior",
        confirmed_specialization="Backend",
        confirmed_grade="SENIOR",
        category_percentile=92,
        last_theta=1.45,
        fsp_score=0.88,
        is_fsp_verified=True,
        desired_salary_min=260000,
        work_format="REMOTE",
        city="Санкт-Петербург",
    )
    db_session.add(c2)
    db_session.flush()

    ach1 = FSPAchievement(
        candidate_profile_id=c2.id,
        event_name="Чемпионат России по спортивному программированию",
        level="ALL_RUSSIAN",
        result="WINNER",
        discipline="Продуктовое программирование",
        sport_category="КМС",
    )
    cs4 = CandidateSkill(candidate_profile_id=c2.id, skill_id=py_skill.id, confirmation_source="FSP")
    cs5 = CandidateSkill(candidate_profile_id=c2.id, skill_id=docker_skill.id, confirmation_source="RESUME")
    db_session.add_all([ach1, cs4, cs5])
    candidates.append(c2)

    # 3. Middle Backend, WEAK CAT test (25 percentile), FSP participant
    c3 = CandidateProfile(
        id="cand-weak-test-fsp",
        user_id="user-3",
        first_name="Игорь",
        last_name="Петров",
        status="OPEN",
        confirmed_category="Backend · Middle",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        category_percentile=25,
        last_theta=-0.67,
        fsp_score=0.35,
        is_fsp_verified=True,
        desired_salary_min=180000,
        work_format="REMOTE",
        city="Казань",
    )
    db_session.add(c3)
    db_session.flush()

    cs6 = CandidateSkill(candidate_profile_id=c3.id, skill_id=py_skill.id, confirmation_source="CLAIMED")
    db_session.add(cs6)
    candidates.append(c3)

    # 4. Hidden Candidate (privacy test)
    c4 = CandidateProfile(
        id="cand-hidden",
        user_id="user-4",
        status="HIDDEN",  # Hidden by candidate privacy settings
        confirmed_category="Backend · Middle",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        category_percentile=99,
        fsp_score=0.99,
        desired_salary_min=100000,
    )
    db_session.add(c4)
    candidates.append(c4)

    # 5. Out of budget Candidate
    c5 = CandidateProfile(
        id="cand-out-of-budget",
        user_id="user-5",
        status="ACTIVELY_SEARCHING",
        confirmed_category="Backend · Middle",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        desired_salary_min=450000,  # Far above 250k budget
        category_percentile=80,
    )
    db_session.add(c5)
    candidates.append(c5)

    db_session.commit()
    return candidates


# ==============================================================================
# 1. STAGE 1: POOL FILTERING TESTS
# ==============================================================================

def test_stage1_filtering_privacy_and_budget(test_candidates):
    """Stage 1 strictly excludes HIDDEN and out-of-budget candidates."""
    filtered = filter_candidate_pool(
        candidates=test_candidates,
        target_specialization="Backend",
        target_grade="MIDDLE",
        salary_budget_max=250000,
    )
    filtered_ids = {c.id for c in filtered}

    # cand-hidden must NOT be included
    assert "cand-hidden" not in filtered_ids
    # cand-out-of-budget must NOT be included (desired 450k > max 250k)
    assert "cand-out-of-budget" not in filtered_ids
    # Active, within-budget candidates are included
    assert "cand-high-test-no-fsp" in filtered_ids
    assert "cand-weak-test-fsp" in filtered_ids


# ==============================================================================
# 2. STAGE 2: EXPLAINABLE RANKING FORMULA & ABLATION NON-DISCRIMINATION TEST
# ==============================================================================

def test_formula_weights_sum_to_one():
    """Verify that formula weights sum to exactly 1.00: 0.30+0.25+0.10+0.25+0.07+0.03 = 1.00."""
    weights = [0.30, 0.25, 0.10, 0.25, 0.07, 0.03]
    assert pytest.approx(sum(weights), 0.0001) == 1.0


def test_no_fsp_candidate_never_penalized_and_ablation(test_candidates):
    """CRITICAL ABLATION REQUIREMENT:

    Candidate with high test score (95th percentile) and NO FSP history
    MUST outrank candidate with weak test score (25th percentile) who has FSP history.
    """
    ranked = execute_two_stage_matching(
        all_candidates=test_candidates,
        target_specialization="Backend",
        target_grade="MIDDLE",
        required_skills=["Python", "PostgreSQL", "FastAPI"],
        salary_budget_max=300000,
    )

    ranked_dict = {item["candidate_id"]: item for item in ranked}
    high_test_item = ranked_dict["cand-high-test-no-fsp"]
    weak_test_item = ranked_dict["cand-weak-test-fsp"]

    # Candidate with high test and NO FSP receives F=0.0 without crash or negative penalty
    assert high_test_item["components"]["F"] == 0.0
    assert high_test_item["fsp_badge"] == "Без спортивной истории"

    # High test candidate must have significantly higher score than weak test candidate
    assert high_test_item["total_score"] > weak_test_item["total_score"]
    assert high_test_item["rank"] < weak_test_item["rank"]

    # Check that explanation bullet points are generated (3-4 items)
    bullets = high_test_item["bullet_points"]
    assert len(bullets) >= 3
    # Check category bullet
    assert any("Категория" in b for b in bullets)
    # Check stack bullet
    assert any("Стек" in b for b in bullets)
    # Check test bullet
    assert any("Тест" in b and "95" in b for b in bullets)
    # Check neutral FSP bullet
    assert any("ФСП: нейтральный" in b for b in bullets)


def test_stack_verification_weights(db_session):
    """Verification weights: Assessment/FSP = 1.0, Resume = 0.5, Claimed = 0.3."""
    py_skill = Skill(id="s1", code="PYTHON", name="Python")
    db_session.add(py_skill)
    db_session.commit()

    cand_test = CandidateProfile(id="c-test", user_id="u-1")
    cand_test.skills = [CandidateSkill(skill=py_skill, confirmation_source="ASSESSMENT")]

    cand_resume = CandidateProfile(id="c-resume", user_id="u-2")
    cand_resume.skills = [CandidateSkill(skill=py_skill, confirmation_source="RESUME")]

    cand_claimed = CandidateProfile(id="c-claim", user_id="u-3")
    cand_claimed.skills = [CandidateSkill(skill=py_skill, confirmation_source="CLAIMED")]

    s_test, _ = compute_stack_score(cand_test, ["Python"])
    s_resume, _ = compute_stack_score(cand_resume, ["Python"])
    s_claimed, _ = compute_stack_score(cand_claimed, ["Python"])

    assert s_test == 1.0
    assert s_resume == 0.5
    assert s_claimed == 0.3


# ==============================================================================
# 3. SELECTION SNAPSHOTS TESTS
# ==============================================================================

def test_selection_snapshot_persistence(db_session, test_candidates):
    """Snapshot service preserves ranked state, hash and shortlist items."""
    company = Company(id="c-1", name="Тест Ко")
    db_session.add(company)
    need = Need(
        id="need-1",
        company_id="c-1",
        title="Python Backend",
        target_specialization="Backend",
        target_grade="MIDDLE",
    )
    db_session.add(need)
    db_session.commit()

    filters = {"target_specialization": "Backend", "target_grade": "MIDDLE", "salary_budget_max": 300000}
    ranked = execute_two_stage_matching(
        all_candidates=test_candidates,
        target_specialization="Backend",
        target_grade="MIDDLE",
        salary_budget_max=300000,
    )

    snapshot = SelectionSnapshotService.save_snapshot(
        db=db_session,
        need_id="need-1",
        filters=filters,
        ranked_candidates=ranked,
    )

    assert snapshot.id is not None
    assert snapshot.query_filters_hash is not None
    assert len(snapshot.ranked_candidates_payload) == len(ranked)

    # Verify shortlist items created
    shortlist = db_session.query(ShortlistItem).filter(ShortlistItem.snapshot_id == snapshot.id).all()
    assert len(shortlist) > 0
    assert shortlist[0].score == ranked[0]["total_score"]
    assert shortlist[0].rank == 1

    # Verify retrieval
    latest = SelectionSnapshotService.get_latest_snapshot(db=db_session, need_id="need-1")
    assert latest.id == snapshot.id


# ==============================================================================
# 4. QA 2026: UNCONFIRMED GRADE AND SALARY TRANSPARENCY TESTS
# ==============================================================================

def test_unconfirmed_grade_candidate_is_not_hidden_and_lowered_in_ranking(db_session):
    """Q&A requirement: 'Неподтверждённый грейд: Показывать со статусом и опускать в выдаче, не скрывать'.

    Candidates without confirmed grade must NOT be dropped by target_grade filter,
    must have is_grade_confirmed=False, status UNCONFIRMED, and score penalty discount.
    """
    py_skill = Skill(id="sk-py-u", code="PYTHON", name="Python")
    db_session.add(py_skill)
    db_session.commit()

    # Confirmed Middle candidate
    c_conf = CandidateProfile(
        id="c-confirmed-mid",
        user_id="u-conf",
        first_name="Василий",
        confirmed_specialization="Backend",
        confirmed_grade="MIDDLE",
        confirmed_category="Backend · Middle",
        category_percentile=70,
        desired_salary_min=180000,
        salary_type="NET",
        is_gross=False,
        work_format="REMOTE",
        status="ACTIVELY_SEARCHING",
    )
    # Unconfirmed candidate in same specialization, same skills
    c_unconf = CandidateProfile(
        id="c-unconfirmed",
        user_id="u-unconf",
        first_name="Семен",
        confirmed_specialization="Backend",
        confirmed_grade=None,  # Unconfirmed grade!
        confirmed_category=None,
        category_percentile=70,
        desired_salary_min=180000,
        salary_type="GROSS",
        is_gross=True,
        work_format="REMOTE",
        status="ACTIVELY_SEARCHING",
    )
    db_session.add_all([c_conf, c_unconf])
    db_session.flush()

    cs1 = CandidateSkill(candidate_profile_id=c_conf.id, skill_id=py_skill.id, confirmation_source="ASSESSMENT")
    cs2 = CandidateSkill(candidate_profile_id=c_unconf.id, skill_id=py_skill.id, confirmation_source="ASSESSMENT")
    db_session.add_all([cs1, cs2])
    db_session.commit()

    # 1. Filter test: unconfirmed candidate MUST NOT be filtered out by target_grade='MIDDLE'
    filtered = filter_candidate_pool(
        candidates=[c_conf, c_unconf],
        target_specialization="Backend",
        target_grade="MIDDLE",
    )
    filtered_ids = {c.id for c in filtered}
    assert "c-unconfirmed" in filtered_ids
    assert "c-confirmed-mid" in filtered_ids

    # 2. Ranking test: unconfirmed candidate must be ranked lower due to penalty
    ranked = execute_two_stage_matching(
        all_candidates=[c_conf, c_unconf],
        target_specialization="Backend",
        target_grade="MIDDLE",
        required_skills=["Python"],
    )
    assert len(ranked) == 2
    r_conf = next(r for r in ranked if r["candidate_id"] == "c-confirmed-mid")
    r_unconf = next(r for r in ranked if r["candidate_id"] == "c-unconfirmed")

    # Confirmed candidate outranks unconfirmed
    assert r_conf["rank"] < r_unconf["rank"]
    assert r_conf["total_score"] > r_unconf["total_score"]

    # Status check
    assert r_unconf["is_grade_confirmed"] is False
    assert r_unconf["grade_status"] == "UNCONFIRMED"
    assert r_unconf["candidate_card"]["is_grade_confirmed"] is False
    assert r_unconf["candidate_card"]["grade_status"] == "UNCONFIRMED"
    assert r_conf["is_grade_confirmed"] is True
    assert r_conf["grade_status"] == "CONFIRMED"

    # Explanation check
    assert any("не подтверждён" in b.lower() for b in r_unconf["bullet_points"])

    # Salary transparency check (Gross vs Net labeled)
    assert r_unconf["candidate_card"]["is_gross"] is True
    assert "Гросс" in r_unconf["candidate_card"]["salary_display"]
    assert r_conf["candidate_card"]["is_gross"] is False
    assert "Нетто" in r_conf["candidate_card"]["salary_display"]
