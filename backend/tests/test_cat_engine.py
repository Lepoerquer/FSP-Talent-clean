"""Tests for the CAT engine, grade rules, assessment API flow and the item bank."""

import os
import random
import sys

import numpy as np
import pytest

BANK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assessment-bank"))
if BANK_DIR not in sys.path:
    sys.path.insert(0, BANK_DIR)

from families.registry import FAMILIES_METADATA, GENERATORS, render_family_item
from validator import MIN_FAMILIES_PER_GRADE, grade_coverage, validate_family_generator, validate_family_metadata

from backend.app.models.assessment import ItemFamily
from backend.app.modules.assessment.cat_engine import (
    EXPOSURE_WARMUP_SESSIONS,
    RANDOMESQUE_TOP_K,
    ItemCandidate,
    filter_eligible_items,
    select_next_item,
)
from backend.app.modules.assessment.grade_rules import evaluate_assessment_result, get_start_theta
from backend.app.modules.assessment.irt import estimate_theta_eap, probability_2pl
from backend.app.modules.assessment.service import sync_item_families_to_db


def make_item(code: str, spec: str = "BACKEND", b: float = 0.0, topic: str = "Python", exposure: int = 0) -> ItemCandidate:
    return ItemCandidate(
        id=code, code=code, specialization=spec, target_grade="MIDDLE", topic=topic,
        discrimination_a=1.2, difficulty_b=b, exposure_count=exposure,
    )


# ==========================================
# Item eligibility and selection
# ==========================================

def test_items_never_come_from_another_specialization():
    pool = [make_item("B1"), make_item("Q1", spec="QA"), make_item("Q2", spec="QA")]
    eligible = filter_eligible_items(pool, "BACKEND", excluded_item_ids={"B1"})
    assert eligible == []


def test_retake_prefers_unseen_families_then_reuses_seen_ones():
    pool = [make_item("B1"), make_item("B2"), make_item("B3")]
    eligible = filter_eligible_items(pool, "BACKEND", excluded_item_ids=set(), history_item_ids={"B1", "B2"})
    assert [it.code for it in eligible] == ["B3"]

    # once the unseen family is used in this session, the retake falls back to earlier families
    eligible = filter_eligible_items(pool, "BACKEND", excluded_item_ids={"B3"}, history_item_ids={"B1", "B2"})
    assert sorted(it.code for it in eligible) == ["B1", "B2"]


def test_exposure_limit_drops_overexposed_families_after_warmup():
    sessions = 100
    pool = [make_item(f"B{i}", exposure=10) for i in range(RANDOMESQUE_TOP_K)] + [make_item("HOT", exposure=60)]
    eligible = filter_eligible_items(pool, "BACKEND", set(), spec_session_count=sessions)
    assert "HOT" not in {it.code for it in eligible}

    # during warmup the rate is not enforced
    eligible = filter_eligible_items(pool, "BACKEND", set(), spec_session_count=EXPOSURE_WARMUP_SESSIONS - 1)
    assert "HOT" in {it.code for it in eligible}


def test_exposure_fallback_keeps_least_exposed_when_all_are_over_limit():
    pool = [make_item(f"B{i}", exposure=50 + i) for i in range(RANDOMESQUE_TOP_K + 3)]
    eligible = filter_eligible_items(pool, "BACKEND", set(), spec_session_count=100)
    assert sorted(it.code for it in eligible) == sorted(f"B{i}" for i in range(RANDOMESQUE_TOP_K))


def test_selection_targets_items_near_current_theta():
    pool = [make_item(f"B{i}", b=b) for i, b in enumerate(np.linspace(-3, 3, 25))]
    rng = random.Random(0)
    for theta in (-2.0, 0.0, 2.0):
        chosen = select_next_item(pool, theta, set(), [], "BACKEND", rng=rng)
        assert abs(chosen.difficulty_b - theta) <= 1.0


# ==========================================
# IRT estimation and grade rules
# ==========================================

def test_start_theta_is_the_centre_of_the_declared_grade():
    assert get_start_theta("INTERN") < get_start_theta("JUNIOR") < get_start_theta("MIDDLE") < get_start_theta("SENIOR")
    assert get_start_theta("middle") == 1.0
    with pytest.raises(ValueError):
        get_start_theta("LEAD")


def test_eap_se_is_posterior_sd_and_shrinks_with_more_items():
    rng = np.random.default_rng(1)
    params = [(1.5, float(b)) for b in rng.uniform(-1, 1, 30)]
    responses = [int(rng.random() < probability_2pl(0.5, a, b)) for a, b in params]

    theta, se = estimate_theta_eap(responses, params)
    nodes = np.linspace(-4, 4, 81)
    log_post = -0.5 * nodes ** 2
    for u, (a, b) in zip(responses, params):
        p = probability_2pl(nodes, a, b)
        log_post += np.log(p if u else 1 - p)
    w = np.exp(log_post - log_post.max())
    w /= w.sum()
    assert theta == pytest.approx(float(np.sum(w * nodes)), abs=1e-9)
    assert se == pytest.approx(float(np.sqrt(np.sum(w * (nodes - theta) ** 2))), abs=1e-9)

    _, se_short = estimate_theta_eap(responses[:5], params[:5])
    assert se < se_short < 1.0


@pytest.mark.parametrize(
    ("grade", "theta", "se", "recommendation"),
    [
        ("MIDDLE", 0.9, 0.3, "GRADE_CONFIRMED"),
        ("MIDDLE", 2.1, 0.3, "OFFER_HIGHER_GRADE"),
        ("MIDDLE", 0.2, 0.3, "OFFER_LOWER_GRADE"),
        ("SENIOR", 2.5, 0.2, "GRADE_CONFIRMED"),
    ],
)
def test_grade_rules(grade, theta, se, recommendation):
    result = evaluate_assessment_result(grade, theta, se)
    assert result.recommendation == recommendation
    assert result.is_confirmed == (recommendation != "OFFER_LOWER_GRADE")
    assert (result.next_grade_change_available_at is not None) == result.is_confirmed


# ==========================================
# Assessment API flow
# ==========================================

def answer_key(item: dict) -> str:
    return render_family_item(item["family_code"], item["seed"]).correct_answer


def test_assessment_session_stays_in_specialization_and_grades_on_completion(client, candidate_headers):
    client.headers.update(candidate_headers)
    start = client.post("/api/v1/assessments/start", json={"specialization": "DATA_ML", "target_grade": "MIDDLE"})
    assert start.status_code == 201
    session = start.json()
    assert session["current_theta"] == get_start_theta("MIDDLE")
    sid = session["session_id"]

    # grading before the stopping rule is refused
    assert client.post(f"/api/v1/assessments/{sid}/finish").status_code == 409

    seen = []
    for _ in range(40):
        item = client.get(f"/api/v1/assessments/{sid}/next").json()
        if item["is_finished"]:
            break
        assert FAMILIES_METADATA[item["family_code"]].specialization == "DATA_ML"
        seen.append(item["family_code"])
        res = client.post(f"/api/v1/assessments/{sid}/answer",
                          json={"session_item_id": item["session_item_id"], "response": answer_key(item)})
        assert res.status_code == 200
        assert res.json()["is_correct"] is True
        if res.json()["is_finished"]:
            break
    assert len(seen) == len(set(seen)), "a family repeated within one session"

    result = client.post(f"/api/v1/assessments/{sid}/finish").json()
    assert result["is_confirmed"] is True
    assert result["final_theta"] > 1.0


def test_assessment_start_rejects_specialization_without_bank(client, candidate_headers):
    res = client.post("/api/v1/assessments/start", json={"specialization": "DEVOPS", "target_grade": "JUNIOR"},
                      headers=candidate_headers)
    assert res.status_code == 422


def test_qualifying_test_needs_a_signed_in_candidate(client, candidate_headers):
    anonymous = client.post("/api/v1/assessments/start", json={"specialization": "QA", "target_grade": "JUNIOR"})
    assert anonymous.status_code == 401

    sid = client.post("/api/v1/assessments/start", json={"specialization": "QA", "target_grade": "JUNIOR"},
                      headers=candidate_headers).json()["session_id"]
    # nobody else can read, answer or grade the candidate's session
    assert client.get(f"/api/v1/assessments/{sid}/next").status_code == 401
    assert client.post(f"/api/v1/assessments/{sid}/finish").status_code == 401
    assert client.get(f"/api/v1/assessments/{sid}/next", headers=candidate_headers).status_code == 200


def test_sync_deactivates_families_missing_from_registry(db_session):
    sync_item_families_to_db(db_session)
    ghost = db_session.query(ItemFamily).first()
    ghost.code = "REMOVED_FAMILY"
    db_session.commit()

    sync_item_families_to_db(db_session)
    assert db_session.query(ItemFamily).filter(ItemFamily.code == "REMOVED_FAMILY").one().is_active is False


# ==========================================
# Data/ML item families (R2 content)
# ==========================================

DATA_ML_CODES = [code for code, meta in FAMILIES_METADATA.items() if meta.specialization == "DATA_ML"]


def test_data_ml_bank_size_and_blueprint_coverage():
    assert len(DATA_ML_CODES) >= 15
    topics = {FAMILIES_METADATA[c].topic for c in DATA_ML_CODES}
    grades = {FAMILIES_METADATA[c].target_grade for c in DATA_ML_CODES}
    assert topics == {"Metrics", "Feature_Engineering", "Models", "Data_Processing"}
    assert grades == {"INTERN", "JUNIOR", "MIDDLE", "SENIOR"}


@pytest.mark.parametrize("code", list(FAMILIES_METADATA))
def test_family_passes_bank_check(code):
    assert validate_family_metadata(FAMILIES_METADATA[code]) == []
    stats = validate_family_generator(code)
    assert stats.errors == []


def test_every_specialization_has_families_on_every_grade():
    for spec, counts in grade_coverage().items():
        assert min(counts.values()) >= MIN_FAMILIES_PER_GRADE, (spec, counts)


@pytest.mark.parametrize("spec", ["BACKEND", "FRONTEND", "QA", "DATA_ML"])
def test_picking_the_longest_option_does_not_pass_junior(spec):
    """A candidate without knowledge who always picks the longest, most detailed option.

    The bank of a specialization is shorter than the test, so a session administers every family.
    Before the options were made parallel this strategy confirmed QA Senior in every attempt.
    """
    rng = random.Random(2026)
    families = [m for m in FAMILIES_METADATA.values() if m.specialization == spec]
    params = [(m.discrimination_a, m.difficulty_b) for m in families]
    thetas = []
    for _ in range(40):
        items = [GENERATORS[m.code](rng.randint(0, 10**6)) for m in families]
        picks = [max(it.options, key=lambda k, it=it: len(it.options[k])) for it in items]
        thetas.append(estimate_theta_eap([int(p == it.correct_answer) for p, it in zip(picks, items)], params)[0])
    assert np.mean(thetas) < -0.5  # below the Junior cut-score


@pytest.mark.parametrize("code", DATA_ML_CODES)
def test_data_ml_family_is_deterministic_per_seed(code):
    assert render_family_item(code, 123).to_full_dict() == render_family_item(code, 123).to_full_dict()
