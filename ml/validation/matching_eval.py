"""Validation of the matching mechanic (plan 6.2): FSP-Talent ranking against baselines.

The synthetic world (ml/synthetic/generator.py) keeps latent and observed attributes apart.
Relevance of a candidate for a need (0-3) is computed from latent attributes only, while every
system, ours included, ranks candidates from observed data only:

  random         hard filters (visibility, format, city, budget), random order
  bm25           hard filters, BM25 of the need text against the resume / profile text
  declared_bm25  hard filters + self-declared specialization and grade (±1), BM25 order:
                 the classic job-board setup
  category       FSP-Talent stage 1 (test-confirmed category), ordered by category match only
  ours           FSP-Talent production ranking (execute_two_stage_matching)
  ours_tuned     the same formula with weights tuned on dev needs
  oracle         sorted by true relevance: the ceiling for this pool

Metrics: P@10 and MRR (relevant = relevance >= 2), nDCG@10 (gain 2^rel - 1), Recall@50.
Weights are tuned on dev needs; headline numbers are on test needs.

Expert annotation (plan 6.2, b): --export-annotation DIR writes a pooled, anonymized sheet for
annotators; --annotations DIR reads the filled copies (one CSV per annotator), reports
Fleiss' kappa and re-scores the systems against the experts' labels.

Usage:
  python ml/validation/matching_eval.py [--candidates 1000] [--needs 50] [--seed 2026]
         [--skip-variants] [--export-annotation DIR] [--annotations DIR] [--strict]
"""

import argparse
import csv
import glob
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import backend.app.models  # noqa: F401  (registers every mapper before profiles are built)
from backend.app.models.candidate import CandidateProfile, CandidateSkill, FSPAchievement
from backend.app.models.dictionary import Skill
from backend.app.modules.assessment.grade_rules import GRADE_CUT_SCORES, GRADE_ORDER
from backend.app.modules.matching.ranking import (
    DEFAULT_WEIGHTS,
    compute_stack_score,
    execute_two_stage_matching,
    filter_candidate_pool,
)
from ml.synthetic.generator import (
    SPECIALIZATIONS,
    SyntheticCandidate,
    SyntheticNeed,
    SyntheticWorldGenerator,
    describe_world,
)
from ml.validation.cat_sim import build_synthetic_bank

COMPONENTS = ["C", "S", "E", "T", "F", "A"]
RELEVANT = 2  # relevance >= 2 counts as a hit for P@10, MRR and Recall@50
FLAT_SOURCE_WEIGHTS = {"ASSESSMENT": 1.0, "TEST": 1.0, "FSP": 1.0, "RESUME": 1.0, "CLAIMED": 1.0}
RANDOM_REPEATS = 20
TUNING_SAMPLES = 3000
BOOTSTRAP_SAMPLES = 5000
TARGET_BANK_FAMILIES = 50
TARGET_BANK_DISCRIMINATION = 1.5

SYSTEMS = {
    "random": "Случайный порядок",
    "bm25": "BM25 по резюме",
    "declared_bm25": "Заявленная категория + BM25",
    "category": "Только подтверждённая категория",
    "ours": "FSP-Talent (формула)",
    "ours_tuned": "FSP-Talent (веса подобраны на dev)",
    "oracle": "Оракул (потолок)",
}
GRADE_RANK = {g: i for i, g in enumerate(GRADE_ORDER)}


# ==========================================
# Ground truth
# ==========================================

def true_relevance(cand: SyntheticCandidate, need: SyntheticNeed) -> int:
    """Relevance 0-3 from latent attributes only (true specialization, grade and skills).

    Same specialization: exact grade gives 2 points, adjacent grade 1, further away is irrelevant;
    true coverage of the required stack adds 1 (>= 75%), 0 (50-75%) or -1 (< 50%).
    Another specialization is at most partially relevant (1) when it truly covers the stack.
    """
    known = cand.true_skills
    coverage = sum(1 for s in need.required_skills if s in known) / len(need.required_skills)
    grade_gap = abs(GRADE_RANK[cand.true_grade] - GRADE_RANK[need.target_grade])
    if cand.specialization != need.target_specialization:
        return 1 if coverage >= 0.75 and grade_gap <= 1 else 0
    if grade_gap >= 2:
        return 0
    grade_points = 2 if grade_gap == 0 else 1
    skill_points = 1 if coverage >= 0.75 else (0 if coverage >= 0.5 else -1)
    return max(0, min(3, grade_points + skill_points))


def true_relevance_with_strength(cand: SyntheticCandidate, need: SyntheticNeed) -> int:
    """Alternative ground truth: the employer also prefers the stronger half of the target grade.

    An exact-grade candidate whose true theta is below the middle of the grade band drops one level.
    """
    rel = true_relevance(cand, need)
    if rel >= RELEVANT and cand.specialization == need.target_specialization and cand.true_grade == need.target_grade:
        lo = GRADE_CUT_SCORES[cand.true_grade]
        nxt = GRADE_RANK[cand.true_grade] + 1
        hi = GRADE_CUT_SCORES[GRADE_ORDER[nxt]] if nxt < len(GRADE_ORDER) else lo + 1.0
        if cand.true_theta < (lo + hi) / 2:
            rel -= 1
    return rel


RELEVANCE_DEFINITIONS = {"fit": true_relevance, "strength": true_relevance_with_strength}


# ==========================================
# Metrics
# ==========================================

def _dcg(rels: list[int]) -> float:
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg_at(ranked: list[int], pool: list[int], k: int = 10) -> float:
    ideal = _dcg(sorted(pool, reverse=True)[:k])
    return _dcg(ranked[:k]) / ideal if ideal > 0 else float("nan")


def precision_at(ranked: list[int], k: int = 10) -> float:
    return sum(r >= RELEVANT for r in ranked[:k]) / k


def reciprocal_rank(ranked: list[int]) -> float:
    return next((1.0 / (i + 1) for i, r in enumerate(ranked) if r >= RELEVANT), 0.0)


def recall_at(ranked: list[int], pool: list[int], k: int = 50) -> float:
    total = sum(r >= RELEVANT for r in pool)
    return sum(r >= RELEVANT for r in ranked[:k]) / total if total else float("nan")


def ranking_metrics(ranking: list[int], rel: np.ndarray, pool: list[int]) -> dict[str, float]:
    ranked = [int(rel[i]) for i in ranking]
    pool_rel = [int(rel[i]) for i in pool]
    return {
        "p10": precision_at(ranked),
        "ndcg10": ndcg_at(ranked, pool_rel),
        "mrr": reciprocal_rank(ranked),
        "recall50": recall_at(ranked, pool_rel),
    }


def mean_metrics(per_need: list[dict[str, float]]) -> dict[str, float]:
    return {k: float(np.nanmean([m[k] for m in per_need])) for k in per_need[0]}


def paired_bootstrap(a: list[float], b: list[float], rng: np.random.Generator) -> dict[str, float]:
    """Mean of a − b over needs with a 95% percentile interval."""
    diff = np.array(a) - np.array(b)
    diff = diff[~np.isnan(diff)]
    samples = rng.choice(diff, size=(BOOTSTRAP_SAMPLES, len(diff)), replace=True).mean(axis=1)
    return {"mean": float(diff.mean()), "ci_low": float(np.percentile(samples, 2.5)),
            "ci_high": float(np.percentile(samples, 97.5)), "n": int(len(diff))}


# ==========================================
# BM25 baseline
# ==========================================

TOKEN_RE = re.compile(r"[\w+#]+")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1]


class BM25:
    """Okapi BM25 (k1 = 1.5, b = 0.75) without stemming, as a plain keyword search would do."""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.tokens = [tokenize(d) for d in docs]
        self.tf = [Counter(t) for t in self.tokens]
        self.lengths = np.array([len(t) for t in self.tokens], dtype=float)
        self.avgdl = float(self.lengths.mean())
        df = Counter(term for t in self.tokens for term in set(t))
        n = len(docs)
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> np.ndarray:
        terms = set(tokenize(query))
        out = np.zeros(len(self.tf))
        norm = self.k1 * (1 - self.b + self.b * self.lengths / self.avgdl)
        for i, tf in enumerate(self.tf):
            out[i] = sum(self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm[i]) for t in terms if t in tf)
        return out


# ==========================================
# World -> platform profiles
# ==========================================

def build_profiles(cands: list[SyntheticCandidate]) -> list[CandidateProfile]:
    """Transient ORM profiles carrying observed attributes only, as the platform would store them."""
    now = datetime.now(timezone.utc)
    skill_objects: dict[str, Skill] = {}
    profiles = []
    for c in cands:
        confirmed = c.confirmed_grade is not None
        profile = CandidateProfile(
            id=c.id,
            user_id=f"user-{c.index}",
            first_name=c.first_name,
            last_name=c.last_name,
            status=c.status,
            confirmed_category=c.confirmed_category,
            confirmed_specialization=c.specialization if confirmed else None,
            confirmed_grade=c.confirmed_grade,
            last_theta=c.theta_hat,
            last_se=c.theta_se,
            category_percentile=c.category_percentile if confirmed else None,
            fsp_score=c.fsp_score,
            is_fsp_verified=bool(c.fsp_achievements),
            desired_salary_min=c.desired_salary_min,
            work_format=c.work_format,
            city=c.city,
            updated_at=now - timedelta(days=c.days_since_update),
        )
        profile.skills = [
            CandidateSkill(skill=skill_objects.setdefault(name, Skill(code=name.upper(), name=name)), confirmation_source=src)
            for name, src in c.skills.items()
        ]
        profile.fsp_achievements = [
            FSPAchievement(event_name=e["event_name"], discipline=e["discipline"], level=e["level"], result=e["result"],
                           sport_category=c.sport_rank, event_date=datetime.fromisoformat(e["event_date"]))
            for e in c.fsp_achievements
        ]
        profiles.append(profile)
    return profiles


@dataclass
class NeedEval:
    need: SyntheticNeed
    pool: list[int]        # candidates passing the employer's hard filters
    rel: np.ndarray        # true relevance for every candidate (0 outside the pool)
    ours: list[int]        # production ranking of the stage-1 pool
    comps: np.ndarray      # components C, S, E, T, F, A of `ours`, row by row
    s_flat: np.ndarray     # S with every skill source weighted equally
    bm25: np.ndarray       # BM25 score of every candidate

    @property
    def has_relevant(self) -> bool:
        return bool((self.rel[self.pool] >= RELEVANT).any())


def need_query(need: SyntheticNeed) -> str:
    return " ".join([need.title, need.raw_description, " ".join(need.required_skills)])


def prepare(world: dict[str, Any], profiles: list[CandidateProfile], relevance=true_relevance) -> list[NeedEval]:
    cands: list[SyntheticCandidate] = world["candidates"]
    by_id = {p.id: i for i, p in enumerate(profiles)}
    bm25 = BM25([c.resume_text for c in cands])
    evals = []
    for need in world["needs"]:
        hard = filter_candidate_pool(profiles, None, None, need.work_format, need.city, need.salary_budget_max)
        pool = [by_id[p.id] for p in hard]
        rel = np.zeros(len(cands), dtype=int)
        for i in pool:
            rel[i] = relevance(cands[i], need)

        ranked = execute_two_stage_matching(
            profiles, need.target_specialization, need.target_grade, need.required_skills,
            need.work_format, need.city, need.salary_budget_max, need.title, need.raw_description,
            top_limit=len(profiles),
        )
        ours = [by_id[r["candidate_id"]] for r in ranked]
        comps = np.array([[r["components"][k] for k in COMPONENTS] for r in ranked], dtype=float).reshape(-1, len(COMPONENTS))
        s_flat = np.array([compute_stack_score(profiles[i], need.required_skills, FLAT_SOURCE_WEIGHTS)[0] for i in ours])
        evals.append(NeedEval(need, pool, rel, ours, comps, s_flat, bm25.scores(need_query(need))))
    return evals


# ==========================================
# Systems
# ==========================================

def rank_with_weights(ne: NeedEval, weights: dict[str, float], flat_skills: bool = False) -> list[int]:
    comps = ne.comps.copy()
    if flat_skills:
        comps[:, COMPONENTS.index("S")] = ne.s_flat
    w = np.array([weights[k] for k in COMPONENTS])
    order = np.argsort(-np.round(comps @ w, 6), kind="stable")
    return [ne.ours[i] for i in order]


def rank_bm25(ne: NeedEval, candidates: list[int]) -> list[int]:
    return sorted(candidates, key=lambda i: -ne.bm25[i])


def rank_declared(ne: NeedEval, cands: list[SyntheticCandidate]) -> list[int]:
    target = GRADE_RANK[ne.need.target_grade]
    eligible = [i for i in ne.pool if cands[i].specialization == ne.need.target_specialization
                and abs(GRADE_RANK[cands[i].declared_grade] - target) <= 1]
    return sorted(eligible, key=lambda i: (cands[i].declared_grade != ne.need.target_grade, -ne.bm25[i]))


def shuffled(items: list[int], rng: random.Random) -> list[int]:
    out = list(items)
    rng.shuffle(out)
    return out


def averaged(rankings: list[list[int]], ne: NeedEval) -> dict[str, float]:
    return mean_metrics([ranking_metrics(r, ne.rel, ne.pool) for r in rankings])


def evaluate_systems(evals: list[NeedEval], cands: list[SyntheticCandidate], tuned: dict[str, float],
                     seed: int) -> dict[str, dict[str, dict[str, float]]]:
    rng = random.Random(seed)
    c_col = COMPONENTS.index("C")
    results: dict[str, dict[str, dict[str, float]]] = {name: {} for name in SYSTEMS}
    for ne in evals:
        nid = ne.need.id
        results["random"][nid] = averaged([shuffled(ne.pool, rng) for _ in range(RANDOM_REPEATS)], ne)
        results["bm25"][nid] = ranking_metrics(rank_bm25(ne, ne.pool), ne.rel, ne.pool)
        results["declared_bm25"][nid] = ranking_metrics(rank_declared(ne, cands), ne.rel, ne.pool)
        c_score = {i: ne.comps[row, c_col] for row, i in enumerate(ne.ours)}
        results["category"][nid] = averaged(
            [sorted(shuffled(ne.ours, rng), key=lambda i: -c_score[i]) for _ in range(RANDOM_REPEATS)], ne)
        results["ours"][nid] = ranking_metrics(ne.ours, ne.rel, ne.pool)
        results["ours_tuned"][nid] = ranking_metrics(rank_with_weights(ne, tuned), ne.rel, ne.pool)
        results["oracle"][nid] = ranking_metrics(sorted(shuffled(ne.pool, rng), key=lambda i: -ne.rel[i]), ne.rel, ne.pool)
    return results


def tune_weights(dev: list[NeedEval], seed: int) -> tuple[dict[str, float], float, float]:
    """Random search over the weight simplex maximising mean nDCG@10 on dev needs."""
    rng = np.random.default_rng(seed)
    default = np.array([DEFAULT_WEIGHTS[k] for k in COMPONENTS])
    grid = np.vstack([default, rng.dirichlet(np.ones(len(COMPONENTS)), size=TUNING_SAMPLES)])
    total = np.zeros(len(grid))
    counted = 0
    for ne in dev:
        if not ne.has_relevant or not ne.ours:
            continue
        ideal = _dcg(sorted((int(r) for r in ne.rel[ne.pool]), reverse=True)[:10])
        rows_rel = ne.rel[ne.ours]
        k = min(10, len(ne.ours))
        top = np.argsort(-(ne.comps @ grid.T), axis=0, kind="stable")[:k]
        discounts = np.log2(np.arange(2, k + 2))[:, None]
        total += ((2.0 ** rows_rel[top] - 1) / discounts).sum(axis=0) / ideal
        counted += 1
    best = int(np.argmax(total))
    return dict(zip(COMPONENTS, (round(float(x), 3) for x in grid[best]))), float(total[best] / counted), float(total[0] / counted)


ABLATIONS = [
    ("full", "Полная формула", {}, False),
    ("no_T", "Без теста (T = 0)", {"T": 0.0}, False),
    ("no_F", "Без ФСП (F = 0)", {"F": 0.0}, False),
    ("no_E", "Без семантики (E = 0)", {"E": 0.0}, False),
    ("no_C", "Без категории (C = 0)", {"C": 0.0}, False),
    ("flat_S", "Без веса подтверждения навыков", {}, True),
]


def evaluate_ablations(evals: list[NeedEval]) -> dict[str, dict[str, float]]:
    out = {}
    for key, label, override, flat in ABLATIONS:
        weights = {**DEFAULT_WEIGHTS, **override}
        per_need = [ranking_metrics(rank_with_weights(ne, weights, flat), ne.rel, ne.pool) for ne in evals]
        out[key] = {"label": label, **mean_metrics(per_need)}
    return out


def fsp_fairness(evals: list[NeedEval], cands: list[SyntheticCandidate]) -> dict[str, float]:
    """Does a missing FSP history push relevant candidates out of the top?"""
    hits: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    pairs = pairs_ok = 0
    top_total = top_no_fsp = rel_total = rel_no_fsp = 0
    for ne in evals:
        top10 = ne.ours[:10]
        relevant = [i for i in ne.pool if ne.rel[i] >= RELEVANT]
        for i in relevant:
            group = "fsp" if cands[i].fsp_achievements else "no_fsp"
            totals[group] += 1
            hits[group] += i in top10
        rel_total += len(relevant)
        rel_no_fsp += sum(1 for i in relevant if not cands[i].fsp_achievements)
        top_total += len(top10)
        top_no_fsp += sum(1 for i in top10 if not cands[i].fsp_achievements)
        position = {i: r for r, i in enumerate(ne.ours)}
        strong = [i for i in ne.ours if ne.rel[i] >= RELEVANT and not cands[i].fsp_achievements]
        weak = [i for i in ne.ours if ne.rel[i] == 0 and cands[i].fsp_achievements]
        for a in strong:
            for b in weak:
                pairs += 1
                pairs_ok += position[a] < position[b]
    return {
        "recall10_relevant_with_fsp": hits["fsp"] / totals["fsp"] if totals["fsp"] else float("nan"),
        "recall10_relevant_without_fsp": hits["no_fsp"] / totals["no_fsp"] if totals["no_fsp"] else float("nan"),
        "share_without_fsp_among_relevant": rel_no_fsp / rel_total if rel_total else float("nan"),
        "share_without_fsp_in_top10": top_no_fsp / top_total if top_total else float("nan"),
        "strong_without_fsp_above_weak_with_fsp": pairs_ok / pairs if pairs else float("nan"),
        "pairs": pairs,
    }


def measure_latency(world: dict[str, Any], profiles: list[CandidateProfile]) -> dict[str, float]:
    times = []
    for need in world["needs"]:
        t0 = time.perf_counter()
        execute_two_stage_matching(profiles, need.target_specialization, need.target_grade, need.required_skills,
                                   need.work_format, need.city, need.salary_budget_max, need.title,
                                   need.raw_description, top_limit=50)
        times.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": float(np.percentile(times, 50)), "p95_ms": float(np.percentile(times, 95)),
            "max_ms": float(max(times)), "candidates": len(profiles)}


# ==========================================
# One world, end to end
# ==========================================

def summarize(results: dict[str, dict[str, dict[str, float]]], need_ids: list[str]) -> dict[str, dict[str, float]]:
    return {name: mean_metrics([per[nid] for nid in need_ids]) for name, per in results.items()}


def evaluate_world(world: dict[str, Any], seed: int, full: bool, relevance=true_relevance) -> dict[str, Any]:
    cands: list[SyntheticCandidate] = world["candidates"]
    profiles = build_profiles(cands)
    evals = prepare(world, profiles, relevance)
    usable = [ne for ne in evals if ne.has_relevant]
    dev = [ne for ne in usable if ne.need.split == "dev"]
    test = [ne for ne in usable if ne.need.split == "test"]

    tuned, dev_tuned, dev_default = tune_weights(dev, seed)
    results = evaluate_systems(usable, cands, tuned, seed)
    test_ids = [ne.need.id for ne in test]
    out: dict[str, Any] = {
        "world": describe_world(world),
        "needs_without_relevant": [ne.need.id for ne in evals if not ne.has_relevant],
        "n_dev": len(dev),
        "n_test": len(test),
        "test": summarize(results, test_ids),
        "dev": summarize(results, [ne.need.id for ne in dev]),
        "tuned_weights": tuned,
        "dev_ndcg10_default": dev_default,
        "dev_ndcg10_tuned": dev_tuned,
    }
    rng = np.random.default_rng(seed)
    out["paired_test"] = {
        f"{system}-{base}": {
            metric: paired_bootstrap([results[system][n][metric] for n in test_ids],
                                     [results[base][n][metric] for n in test_ids], rng)
            for metric in ("ndcg10", "p10")
        }
        for system, base in PAIRED_COMPARISONS
    }
    out["ablations_test"] = evaluate_ablations(test)
    if not full:
        return out

    out["fsp_fairness"] = fsp_fairness(usable, cands)
    out["latency"] = measure_latency(world, profiles)
    out["per_need"] = {
        ne.need.id: {"title": ne.need.title, "split": ne.need.split, "source": ne.need.source,
                     "pool": len(ne.pool), "stage1_pool": len(ne.ours),
                     "relevant": int((ne.rel[ne.pool] >= RELEVANT).sum()),
                     **{name: results[name][ne.need.id] for name in ("bm25", "declared_bm25", "ours", "oracle")}}
        for ne in usable
    }
    out["_evals"] = evals  # kept in memory for the annotation tools, dropped before saving
    return out


PAIRED_COMPARISONS = [
    ("ours", "bm25"), ("ours", "declared_bm25"), ("ours", "category"), ("ours", "random"),
    ("ours_tuned", "ours"), ("ours_tuned", "bm25"), ("ours_tuned", "declared_bm25"),
]
PAIRED_LABELS = {
    "ours-bm25": "FSP-Talent − BM25",
    "ours-declared_bm25": "FSP-Talent − заявленная категория + BM25",
    "ours-category": "FSP-Talent − только категория",
    "ours-random": "FSP-Talent − случайный",
    "ours_tuned-ours": "Подобранные веса − исходные",
    "ours_tuned-bm25": "Подобранные веса − BM25",
    "ours_tuned-declared_bm25": "Подобранные веса − заявленная категория + BM25",
}


def target_bank_pool(seed: int) -> list:
    rng = random.Random(seed)
    pool = []
    for spec in SPECIALIZATIONS:
        pool += [it.engine for it in build_synthetic_bank(spec, TARGET_BANK_FAMILIES, TARGET_BANK_DISCRIMINATION, rng)[spec]]
    return pool


# ==========================================
# Expert annotation (plan 6.2, b)
# ==========================================

SOURCE_RU = {"ASSESSMENT": "тест", "TEST": "тест", "FSP": "ФСП", "RESUME": "резюме", "CLAIMED": "заявлен"}


def candidate_card(c: SyntheticCandidate) -> str:
    """What an employer sees before an invitation: no name, no contacts."""
    skills = ", ".join(f"{s} [{SOURCE_RU.get(src, src)}]" for s, src in sorted(c.skills.items()))
    category = f"{c.confirmed_category}, процентиль {c.category_percentile}" if c.confirmed_grade else "грейд не подтверждён"
    fsp = f"ФСП: {len(c.fsp_achievements)} достиж., балл {c.fsp_score:.2f}" if c.fsp_achievements else "ФСП: истории нет"
    resume = re.sub(r"^[^\n]*\.\s", "", c.resume_text, count=1)  # drop the name line
    return (f"Категория по тесту: {category}. Заявленный грейд: {c.declared_grade}. Навыки: {skills}. {fsp}. "
            f"Ожидания: от {c.desired_salary_min} ₽, {c.work_format}, {c.city}.\nРезюме: {resume}")


def export_annotation(evals: list[NeedEval], cands: list[SyntheticCandidate], directory: str, seed: int,
                      n_needs: int = 10, depth: int = 20) -> None:
    """Pool the top of our ranking and of BM25 (TREC-style) for test needs, shuffled and anonymized."""
    rng = random.Random(seed)
    test = [ne for ne in evals if ne.need.split == "test" and ne.has_relevant]
    by_spec = [[ne for ne in test if ne.need.target_specialization == spec] for spec in SPECIALIZATIONS]
    chosen = []
    while len(chosen) < n_needs and any(by_spec):  # round-robin across specializations
        for group in by_spec:
            if group and len(chosen) < n_needs:
                chosen.append(group.pop(0))
    rows, key = [], {}
    for ne in chosen:
        pooled = list(dict.fromkeys(ne.ours[:depth] + rank_bm25(ne, ne.pool)[:depth]))
        rng.shuffle(pooled)
        for i in pooled:
            item_id = f"{ne.need.id}-{len(key) + 1:04d}"
            key[item_id] = {"need_id": ne.need.id, "candidate_id": cands[i].id}
            rows.append({
                "item_id": item_id, "need_id": ne.need.id, "need_title": ne.need.title,
                "need_text": ne.need.raw_description, "required_skills": ", ".join(ne.need.required_skills),
                "candidate_card": candidate_card(cands[i]), "relevance_0_3": "",
            })
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "annotation_template.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(directory, "annotation_key.json"), "w", encoding="utf-8") as f:
        json.dump(key, f, ensure_ascii=False, indent=2)
    with open(os.path.join(directory, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Экспертная разметка подбора\n\n"
            "1. Каждый разметчик копирует `annotation_template.csv` в файл со своим именем (например `r1.csv`) "
            "и не смотрит разметку коллег.\n"
            "2. В столбце `relevance_0_3` ставит оценку: 3 — пригласил бы в первую очередь, 2 — подходит, "
            "1 — частично подходит, 0 — не подходит.\n"
            "3. Файл `annotation_key.json` не открывать до конца разметки.\n"
            "4. Результат: `python ml/validation/matching_eval.py --annotations <эта папка>`.\n"
        )
    print(f"Annotation sheet: {len(rows)} items for {len(chosen)} needs -> {directory}")


def fleiss_kappa(ratings: np.ndarray, categories: int = 4) -> float:
    """ratings: items x raters, integer labels 0..categories-1."""
    n_items, n_raters = ratings.shape
    counts = np.zeros((n_items, categories))
    for c in range(categories):
        counts[:, c] = (ratings == c).sum(axis=1)
    p_j = counts.sum(axis=0) / (n_items * n_raters)
    p_i = ((counts ** 2).sum(axis=1) - n_raters) / (n_raters * (n_raters - 1))
    p_bar, p_e = p_i.mean(), (p_j ** 2).sum()
    return float((p_bar - p_e) / (1 - p_e)) if p_e < 1 else 1.0


def weighted_kappa(a: np.ndarray, b: np.ndarray, categories: int = 4) -> float:
    """Cohen's kappa with quadratic weights."""
    observed = np.zeros((categories, categories))
    for x, y in zip(a, b):
        observed[x, y] += 1
    observed /= observed.sum()
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0))
    idx = np.arange(categories)
    weights = (idx[:, None] - idx[None, :]) ** 2 / (categories - 1) ** 2
    denom = (weights * expected).sum()
    return float(1 - (weights * observed).sum() / denom) if denom > 0 else 1.0


def score_annotations(evals: list[NeedEval], cands: list[SyntheticCandidate], directory: str) -> dict[str, Any]:
    with open(os.path.join(directory, "annotation_key.json"), encoding="utf-8") as f:
        key = json.load(f)
    files = sorted(p for p in glob.glob(os.path.join(directory, "*.csv")) if not p.endswith("annotation_template.csv"))
    labels: dict[str, list[int]] = {}
    for path in files:
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row["relevance_0_3"].strip():
                    labels.setdefault(row["item_id"], []).append(int(row["relevance_0_3"]))
    complete = {item: v for item, v in labels.items() if len(v) == len(files)}
    if len(files) < 2 or not complete:
        raise SystemExit(f"Need at least two filled annotation files in {directory}")
    items = sorted(complete)
    matrix = np.array([complete[i] for i in items])
    pairwise = [weighted_kappa(matrix[:, a], matrix[:, b]) for a in range(len(files)) for b in range(a + 1, len(files))]
    consensus = {i: int(np.median(complete[i])) for i in items}

    by_need = {ne.need.id: ne for ne in evals}
    cand_index = {c.id: n for n, c in enumerate(cands)}
    latent = np.array([by_need[key[i]["need_id"]].rel[cand_index[key[i]["candidate_id"]]] for i in items])
    expert = np.array([consensus[i] for i in items])

    rescored: dict[str, list[dict[str, float]]] = {"ours": [], "bm25": []}
    for need_id in sorted({key[i]["need_id"] for i in items}):
        ne = by_need[need_id]
        expert_rel = np.zeros(len(cands), dtype=int)  # unjudged candidates count as irrelevant
        for i in items:
            if key[i]["need_id"] == need_id:
                expert_rel[cand_index[key[i]["candidate_id"]]] = consensus[i]
        rescored["ours"].append(ranking_metrics(ne.ours, expert_rel, ne.pool))
        rescored["bm25"].append(ranking_metrics(rank_bm25(ne, ne.pool), expert_rel, ne.pool))
    return {
        "annotators": len(files),
        "items": len(items),
        "fleiss_kappa": fleiss_kappa(matrix),
        "pairwise_weighted_kappa": pairwise,
        "expert_vs_latent_weighted_kappa": weighted_kappa(expert, latent),
        "rescored_by_experts": {k: mean_metrics(v) for k, v in rescored.items()},
    }


# ==========================================
# Report
# ==========================================

def fmt(x: float, digits: int = 3) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}"


def pct(x: float) -> str:
    return "—" if x is None or math.isnan(x) else f"{x * 100:.1f}%"


def systems_table(summary: dict[str, dict[str, float]]) -> list[str]:
    lines = ["| Система | P@10 | nDCG@10 | MRR | Recall@50 |", "|---|---|---|---|---|"]
    for key, label in SYSTEMS.items():
        m = summary[key]
        bold = "**" if key == "ours" else ""
        lines.append(f"| {bold}{label}{bold} | {fmt(m['p10'])} | {fmt(m['ndcg10'])} | {fmt(m['mrr'])} | {fmt(m['recall50'])} |")
    return lines


def ci_text(d: dict[str, float]) -> str:
    return f"{d['mean']:+.3f} [{d['ci_low']:+.3f}; {d['ci_high']:+.3f}]"


def verdict(d: dict[str, float]) -> str:
    if d["ci_low"] > 0:
        return "выше, разница значима"
    if d["ci_high"] < 0:
        return "ниже, разница значима"
    return "разница незначима"


def key_findings(report: dict[str, Any]) -> list[str]:
    main = report["main"]
    pt = main["paired_test"]
    lines = []
    for key in ("ours-bm25", "ours-declared_bm25", "ours_tuned-ours", "ours_tuned-declared_bm25"):
        d = pt[key]["ndcg10"]
        lines.append(f"- {PAIRED_LABELS[key]}: Δ nDCG@10 {ci_text(d)} — {verdict(d)}.")
    target = report["variants"].get("target_bank")
    if target:
        d = target["paired_test"]["ours-declared_bm25"]["ndcg10"]
        lines.append(f"- С целевым банком заданий: FSP-Talent − заявленная категория + BM25 Δ nDCG@10 {ci_text(d)} — {verdict(d)}.")
    full = main["ablations_test"]["full"]["ndcg10"]
    notes = {
        "no_F": "эталон учитывает только соответствие вакансии, а ФСП по ТЗ — бонус внутри категории, "
                "так что небольшая цена ожидаема",
        "flat_S": f"ложных среди непроверенных навыков в профилях {pct(main['world']['false_unverified_skill_share'])}, "
                  "а скидка 0,3–0,5 рассчитана на гораздо большую долю",
    }
    for key, row in main["ablations_test"].items():
        if key != "full" and row["ndcg10"] - full > 0.01:
            note = notes.get(key, "при текущих весах эта часть формулы мешает")
            lines.append(f"- Вариант «{row['label']}» лучше полной формулы на {row['ndcg10'] - full:+.3f} nDCG@10: {note}.")
    ts = report["variants"].get("target_bank_strength")
    if ts:
        def no_t(result: dict[str, Any]) -> float:
            return result["ablations_test"]["no_T"]["ndcg10"] - result["ablations_test"]["full"]["ndcg10"]
        lines.append(f"- Вклад T зависит от точности теста: убрать T выгодно на {no_t(main):+.3f} при текущем банке, "
                     f"но только на {no_t(ts):+.3f} с целевым банком, если работодатель ценит силу внутри грейда. "
                     "Вес T = 0,25 завышен для нынешней точности теста.")
    ff = main["fsp_fairness"]
    lines.append(f"- Кандидаты без ФСП не вытесняются: в {pct(ff['strong_without_fsp_above_weak_with_fsp'])} пар "
                 "релевантный кандидат без ФСП стоит выше нерелевантного с ФСП.")
    lines.append(f"- p95 времени подбора {main['latency']['p95_ms']:.0f} мс на {main['latency']['candidates']} кандидатах.")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    main = report["main"]
    w = main["world"]
    lines = [
        "# Валидация механики подбора",
        "",
        f"Сгенерировано `ml/validation/matching_eval.py` (seed {report['seed']}). Воспроизводится командой "
        "`make validate-matching`.",
        "",
        "## Главное",
        "",
        *key_findings(report),
        "",
        "## Постановка",
        "",
        f"- Синтетический мир: {w['candidates']} кандидатов, {w['needs']} потребностей "
        f"({report['reference_needs']} написаны вручную, остальные по шаблонам), {w['companies']} компаний. "
        f"Потребности поделены на dev ({main['n_dev']}) и test ({main['n_test']}) поровну внутри каждой специализации: "
        "веса подбираются только на dev, все итоговые цифры — на test.",
        "- Эталон релевантности 0–3 строится только по скрытым атрибутам: истинная специализация, истинный грейд "
        "и навыки, которыми кандидат реально владеет. Ни одна система их не видит.",
        "- Все системы видят одно и то же: анкету, заявленный грейд, результат теста (реальный CAT-движок на текущем "
        "банке заданий), навыки с источником подтверждения, достижения ФСП, текст резюме. Жёсткие условия "
        "работодателя (формат, город, бюджет, скрытые профили) одинаковы для всех систем.",
        "",
        "| Релевантность | Та же специализация | Другая специализация |",
        "|---|---|---|",
        "| 3 | грейд совпадает, стек освоен на ≥ 75 % | — |",
        "| 2 | грейд совпадает и стек 50–75 %, или соседний грейд и стек ≥ 75 % | — |",
        "| 1 | остальные сочетания с грейдом ±1 | грейд ±1 и стек ≥ 75 % |",
        "| 0 | грейд отличается на 2 и больше, или соседний грейд и стек < 50 % | иначе |",
        "",
        f"Релевантным для P@10, MRR и Recall@50 считается уровень ≥ {RELEVANT}; nDCG@10 использует все уровни.",
        "",
        "Свойства мира, которые влияют на результат:",
        f"- грейд подтверждён тестом у {pct(w['grade_confirmed'])} кандидатов; подтверждённый грейд совпадает с "
        f"истинным у {pct(w['confirmed_grade_accuracy'])}, заявленный самим кандидатом — у {pct(w['declared_grade_accuracy'])};",
        f"- история ФСП у {pct(w['with_fsp'])}, корреляция FSP-score с истинной θ {w['fsp_theta_correlation']:.2f} (слабая по плану);",
        f"- резюме загружено у {pct(w['with_resume'])}, накрутка ключевых слов в резюме у {pct(w['keyword_stuffers'])}; "
        f"среди навыков из резюме и анкеты ложных {pct(w['false_unverified_skill_share'])}.",
        "",
        f"## Результаты на тестовых потребностях ({main['n_test']})",
        "",
        *systems_table(main["test"]),
        "",
        "Разница с базовыми линиями (парный бутстрэп по потребностям, 95 % интервал):",
        "",
        "| Сравнение | Δ nDCG@10 | Δ P@10 |",
        "|---|---|---|",
    ]
    for key, label in PAIRED_LABELS.items():
        d = main["paired_test"][key]
        lines.append(f"| {label} | {ci_text(d['ndcg10'])} | {ci_text(d['p10'])} |")

    lines += [
        "",
        "## Абляции (test)",
        "",
        "| Вариант формулы | P@10 | nDCG@10 | Δ nDCG@10 к полной |",
        "|---|---|---|---|",
    ]
    full = main["ablations_test"]["full"]["ndcg10"]
    for row in main["ablations_test"].values():
        lines.append(f"| {row['label']} | {fmt(row['p10'])} | {fmt(row['ndcg10'])} | {row['ndcg10'] - full:+.3f} |")

    tw = main["tuned_weights"]
    lines += [
        "",
        "## Подбор весов (dev → test)",
        "",
        f"Случайный поиск по симплексу весов ({TUNING_SAMPLES} вариантов), критерий — средний nDCG@10 на dev.",
        "",
        "| | C | S | E | T | F | A | nDCG@10 dev | nDCG@10 test |",
        "|---|---|---|---|---|---|---|---|---|",
        "| Исходные веса | " + " | ".join(f"{DEFAULT_WEIGHTS[k]:.2f}" for k in COMPONENTS)
        + f" | {fmt(main['dev_ndcg10_default'])} | {fmt(main['test']['ours']['ndcg10'])} |",
        "| Подобранные | " + " | ".join(f"{tw[k]:.2f}" for k in COMPONENTS)
        + f" | {fmt(main['dev_ndcg10_tuned'])} | {fmt(main['test']['ours_tuned']['ndcg10'])} |",
        "",
        "Подобранные веса опираются на синтетику: например, E (пересечение слов) заодно штрафует резюме с накруткой "
        "ключевых слов. Переносить их в прод стоит после проверки на экспертной разметке.",
        "",
        "## Кандидаты без истории ФСП",
        "",
    ]
    ff = main["fsp_fairness"]
    lines += [
        f"- Доля релевантных кандидатов, попавших в топ-10: с историей ФСП {pct(ff['recall10_relevant_with_fsp'])}, "
        f"без истории {pct(ff['recall10_relevant_without_fsp'])}.",
        f"- Кандидатов без ФСП среди релевантных {pct(ff['share_without_fsp_among_relevant'])}, "
        f"в топ-10 {pct(ff['share_without_fsp_in_top10'])}.",
        f"- В {pct(ff['strong_without_fsp_above_weak_with_fsp'])} из {ff['pairs']} пар релевантный кандидат без ФСП "
        "стоит выше нерелевантного кандидата с ФСП.",
        "",
        "## Скорость",
        "",
        f"Функция подбора на {main['latency']['candidates']} кандидатах в памяти: p50 {main['latency']['p50_ms']:.0f} мс, "
        f"p95 {main['latency']['p95_ms']:.0f} мс, максимум {main['latency']['max_ms']:.0f} мс "
        "(без времени запроса к БД; цель плана для API — p95 ≤ 500 мс).",
    ]

    if report.get("variants"):
        lines += ["", "## Чувствительность к допущениям", ""]
        for key, variant in report["variants"].items():
            vw = variant["world"]
            abl = variant["ablations_test"]
            full = abl["full"]["ndcg10"]
            vt = variant["tuned_weights"]
            lines += [
                f"### {variant['label']}",
                "",
                f"Подтверждённый грейд верен у {pct(vw['confirmed_grade_accuracy'])}, накрутка у {pct(vw['keyword_stuffers'])}.",
                "",
                *systems_table(variant["test"]),
                "",
                "Абляции (Δ nDCG@10 к полной формуле): "
                + ", ".join(f"{row['label'][0].lower()}{row['label'][1:]} {row['ndcg10'] - full:+.3f}" for k, row in abl.items() if k != "full")
                + ". Подобранные веса: " + ", ".join(f"{k} {vt[k]:.2f}" for k in COMPONENTS) + ".",
                "",
            ]

    if report.get("annotation"):
        a = report["annotation"]
        lines += [
            "## Экспертная разметка",
            "",
            f"Разметчиков: {a['annotators']}, пар «потребность — кандидат»: {a['items']}. κ Флейса {a['fleiss_kappa']:.2f}; "
            f"попарная взвешенная κ: {', '.join(f'{k:.2f}' for k in a['pairwise_weighted_kappa'])}. "
            f"Согласие медианной экспертной оценки с эталоном по скрытым атрибутам: взвешенная κ "
            f"{a['expert_vs_latent_weighted_kappa']:.2f}.",
            "",
            "| Система | P@10 | nDCG@10 (по оценкам экспертов) |",
            "|---|---|---|",
            f"| FSP-Talent | {fmt(a['rescored_by_experts']['ours']['p10'])} | {fmt(a['rescored_by_experts']['ours']['ndcg10'])} |",
            f"| BM25 | {fmt(a['rescored_by_experts']['bm25']['p10'])} | {fmt(a['rescored_by_experts']['bm25']['ndcg10'])} |",
            "",
        ]

    lines += [
        "",
        "## Ограничения",
        "",
        "- Данные синтетические, а эталон релевантности задан формулой: цифры показывают, как механика ведёт себя "
        "при принятых допущениях, а не на реальном рынке. Экспертная разметка (`--export-annotation`) проверяет "
        "сам эталон.",
        "- Тест подтверждает грейд реальным движком на текущем банке, поэтому качество подбора зависит от наполнения "
        "банка (см. отчёт `cat_sim_report.md` и вариант с целевым банком выше).",
        "- BM25 без стемминга: для русского текста это ослабляет базовую линию по описаниям, но навыки "
        "в вакансиях и резюме записаны одинаково.",
    ]
    return "\n".join(lines) + "\n"


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [jsonable(v) for v in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--candidates", type=int, default=1000)
    parser.add_argument("--needs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--skip-variants", action="store_true", help="only the main world")
    parser.add_argument("--export-annotation", metavar="DIR", help="write an expert annotation sheet")
    parser.add_argument("--annotations", metavar="DIR", help="score filled annotation sheets")
    parser.add_argument("--strict", action="store_true", help="exit 1 unless ours beats BM25 on test nDCG@10")
    args = parser.parse_args()

    t0 = time.time()
    print("[MATCHING] main world (current item bank)...")
    world = SyntheticWorldGenerator(seed=args.seed).generate_world(args.candidates, args.needs)
    main_result = evaluate_world(world, args.seed, full=True)
    evals = main_result.pop("_evals")

    report: dict[str, Any] = {
        "seed": args.seed,
        "reference_needs": sum(1 for n in world["needs"] if n.source == "reference"),
        "main": main_result,
        "variants": {},
    }
    if not args.skip_variants:
        print("[MATCHING] generating variant worlds...")
        target_world = SyntheticWorldGenerator(seed=args.seed, item_pool=target_bank_pool(args.seed)).generate_world(
            args.candidates, args.needs)
        clean_world = SyntheticWorldGenerator(seed=args.seed, keyword_stuffing_rate=0.0).generate_world(
            args.candidates, args.needs)
        target_label = f"целевой банк ({TARGET_BANK_FAMILIES} откалиброванных семейств на специализацию, a = {TARGET_BANK_DISCRIMINATION})"
        variants = {
            "target_bank": (target_label.capitalize(), target_world, "fit"),
            "no_stuffing": ("Без накрутки ключевых слов в резюме", clean_world, "fit"),
            "strength": ("Эталон ценит силу внутри грейда (слабая половина грейда на уровень ниже)", world, "strength"),
            "target_bank_strength": (f"Эталон ценит силу внутри грейда, {target_label}", target_world, "strength"),
        }
        for key, (label, vworld, relevance) in variants.items():
            print(f"[MATCHING] variant {key}...")
            report["variants"][key] = {"label": label, **evaluate_world(vworld, args.seed, full=False,
                                                                       relevance=RELEVANCE_DEFINITIONS[relevance])}

    if args.export_annotation:
        export_annotation(evals, world["candidates"], args.export_annotation, args.seed)
    if args.annotations:
        report["annotation"] = score_annotations(evals, world["candidates"], args.annotations)

    report["elapsed_seconds"] = round(time.time() - t0, 1)
    json_path = os.path.join(CURRENT_DIR, "matching_report.json")
    md_path = os.path.join(CURRENT_DIR, "matching_report.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(jsonable(report), f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))

    test = main_result["test"]
    print(f"\nTest needs: {main_result['n_test']}")
    for key, label in SYSTEMS.items():
        m = test[key]
        print(f"  {key:<14} P@10 {m['p10']:.3f}  nDCG@10 {m['ndcg10']:.3f}  MRR {m['mrr']:.3f}  R@50 {m['recall50']:.3f}")
    print(f"\nReports: {json_path}\n         {md_path}  ({report['elapsed_seconds']}s)")

    if args.strict and test["ours"]["ndcg10"] <= test["bm25"]["ndcg10"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
