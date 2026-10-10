"""Tests for ranking parameters, skill matching and the matching validation harness."""

import numpy as np
import pytest

from backend.app.models.candidate import CandidateProfile, CandidateSkill
from backend.app.models.dictionary import Skill
from backend.app.modules.dictionaries.seeds import SPECIALIZATIONS_DATA
from backend.app.modules.matching.ranking import (
    DEFAULT_WEIGHTS,
    compute_stack_score,
    is_related_specialization,
    normalize_token,
    rank_and_explain_candidate,
    skills_match,
)
from ml.synthetic.generator import TRACKS, SyntheticWorldGenerator
from ml.validation import matching_eval as me


def profile_with(skills: dict[str, str]) -> CandidateProfile:
    cand = CandidateProfile(id="c-1", user_id="u-1", confirmed_specialization="BACKEND", confirmed_grade="MIDDLE",
                            category_percentile=70, status="ACTIVELY_SEARCHING")
    cand.skills = [CandidateSkill(skill=Skill(code=n.upper(), name=n), confirmation_source=src) for n, src in skills.items()]
    return cand


# ==========================================
# Ranking: skill matching, weights, dictionary codes
# ==========================================

@pytest.mark.parametrize(
    ("required", "have", "expected"),
    [
        ("Go", "Go (Golang)", True),
        ("Go", "Django", False),
        ("Go", "MongoDB", False),
        ("Java", "JavaScript", False),
        ("Spring", "Spring Boot", True),
        ("Postman / Newman", "Postman / Newman", True),
    ],
)
def test_skills_match_whole_words_only(required, have, expected):
    assert skills_match(normalize_token(required), normalize_token(have)) is expected


def test_stack_score_does_not_credit_javascript_for_java():
    score, _ = compute_stack_score(profile_with({"JavaScript": "ASSESSMENT"}), ["Java"])
    assert score == 0.0


def test_stack_score_source_weights_are_configurable():
    cand = profile_with({"Python": "CLAIMED", "Django": "RESUME"})
    default, _ = compute_stack_score(cand, ["Python", "Django"])
    flat, _ = compute_stack_score(cand, ["Python", "Django"], source_weights=me.FLAT_SOURCE_WEIGHTS)
    assert default == pytest.approx((0.3 + 0.5) / 2)
    assert flat == 1.0


def test_custom_weights_change_the_total_score():
    cand = profile_with({"Python": "ASSESSMENT"})
    only_stack = {k: 0.0 for k in DEFAULT_WEIGHTS} | {"S": 1.0}
    result = rank_and_explain_candidate(cand, "BACKEND", "MIDDLE", ["Python"], weights=only_stack)
    assert result["total_score"] == result["components"]["S"] == 1.0
    assert result["weights"] == only_stack
    assert rank_and_explain_candidate(cand, "BACKEND", "MIDDLE", ["Python"])["weights"] == DEFAULT_WEIGHTS


def test_data_ml_code_is_shared_by_dictionary_bank_and_matching():
    codes = {s["code"]: s for s in SPECIALIZATIONS_DATA}
    assert "DATA_ML" in codes and "DATA_SCIENCE" not in codes
    assert codes["DEVOPS"]["has_active_assessment"] == 0
    assert is_related_specialization("DATA_ML", "BACKEND")
    assert is_related_specialization("BACKEND", "DATA_ML")


# ==========================================
# Metrics and baselines
# ==========================================

def test_ranking_metrics_on_a_hand_computed_case():
    rel = np.array([3, 0, 2, 0, 1])
    pool = [0, 1, 2, 3, 4]
    perfect = me.ranking_metrics([0, 2, 4, 1, 3], rel, pool)
    assert perfect["ndcg10"] == pytest.approx(1.0)
    assert perfect["p10"] == pytest.approx(0.2)
    assert perfect["mrr"] == 1.0
    assert perfect["recall50"] == 1.0

    worst = me.ranking_metrics([1, 3, 4, 2, 0], rel, pool)
    assert worst["mrr"] == pytest.approx(1 / 4)
    assert worst["ndcg10"] < 0.6


def test_bm25_prefers_documents_with_rare_query_terms():
    bm25 = me.BM25(["python django postgresql", "java spring", "python flask", "javascript react"])
    scores = bm25.scores("python django")
    assert int(np.argmax(scores)) == 0
    assert scores[3] == 0.0


def test_kappas_on_perfect_and_chance_agreement():
    labels = np.array([0, 1, 2, 3, 0, 1, 2, 3])
    assert me.weighted_kappa(labels, labels) == pytest.approx(1.0)
    assert me.fleiss_kappa(np.stack([labels, labels, labels], axis=1)) == pytest.approx(1.0)
    assert me.weighted_kappa(labels, labels[::-1]) < 0.5


# ==========================================
# Synthetic world and ground truth
# ==========================================

@pytest.fixture(scope="module")
def small_world():
    return SyntheticWorldGenerator(seed=7).generate_world(n_candidates=160, n_needs=16)


def test_generator_is_deterministic_and_keeps_latent_world_across_variants(small_world):
    again = SyntheticWorldGenerator(seed=7).generate_world(n_candidates=160, n_needs=16)
    assert [c.to_dict() for c in again["candidates"]] == [c.to_dict() for c in small_world["candidates"]]

    clean = SyntheticWorldGenerator(seed=7, keyword_stuffing_rate=0.0).generate_world(n_candidates=160, n_needs=16)
    for a, b in zip(clean["candidates"], small_world["candidates"]):
        assert (a.true_theta, a.true_grade, a.mastery) == (b.true_theta, b.true_grade, b.mastery)
        assert not a.keyword_stuffer
    assert [n.required_skills for n in clean["needs"]] == [n.required_skills for n in small_world["needs"]]


def test_world_uses_dictionary_skill_names_and_splits_needs(small_world):
    track_skills = {s for spec in TRACKS.values() for tr in spec.values() for s in tr["core"] + tr["extra"]}
    for cand in small_world["candidates"]:
        assert set(cand.mastery) <= track_skills
    splits = {n.split for n in small_world["needs"]}
    assert splits == {"dev", "test"}
    assert sum(n.source == "reference" for n in small_world["needs"]) == 10


def test_true_relevance_uses_latent_attributes_only(small_world):
    need = small_world["needs"][0]
    cand = next(c for c in small_world["candidates"] if c.specialization == need.target_specialization)
    cand.true_grade = need.target_grade
    cand.mastery = {s: 0.9 for s in need.required_skills}
    cand.declared_grade, cand.confirmed_grade = "INTERN", None  # observed attributes must not matter
    assert me.true_relevance(cand, need) == 3

    cand.mastery = {}
    assert me.true_relevance(cand, need) == 1


def test_evaluation_runs_end_to_end_and_beats_random(small_world):
    result = me.evaluate_world(small_world, seed=7, full=True)
    test = result["test"]
    assert result["n_test"] > 0
    assert test["oracle"]["ndcg10"] == pytest.approx(1.0)
    assert test["ours"]["ndcg10"] > test["random"]["ndcg10"]
    assert set(result["ablations_test"]) == {key for key, *_ in me.ABLATIONS}
    assert 0.0 <= result["fsp_fairness"]["strong_without_fsp_above_weak_with_fsp"] <= 1.0
