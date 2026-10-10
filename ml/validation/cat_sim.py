"""Psychometric simulation of the CAT engine (validation of the testing mechanic, plan 6.3).

Synthetic candidates with a known ("true") ability answer items according to the 2PL model,
while the production engine (cat_engine, irt, grade_rules) selects items, estimates theta and
applies the grade rules. The engine only sees responses and the bank's item parameters.

Scenarios:
  real            the current bank, each specialization on its own families
  real_b_noise    true difficulties differ from the bank's by N(0, 0.3): calibration error
  real_true_a1    true discrimination is 1.0 while the bank claims more: overstated a
  bank sweep      synthetic calibrated banks of growing size for one specialization, to show
                  how many families are needed for the exposure and retest targets
  zero knowledge  candidates who know nothing and pick an option by its form (longest, shortest)
                  or at random, answering real rendered items: the bank must not reward test-wiseness

Each candidate takes the test twice; the retake avoids families seen in the first session,
as the production engine does, so test-retest agreement is measured on different items.

Usage:
  python ml/validation/cat_sim.py [--n 1000] [--seed 2026] [--skip-sweep] [--strict]
"""

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.stats import pearsonr

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
BANK_DIR = os.path.join(PROJECT_ROOT, "assessment-bank")
for p in [PROJECT_ROOT, BANK_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from families.registry import GENERATORS, list_all_families

from backend.app.modules.assessment.cat_engine import (
    BLUEPRINTS,
    MAX_ITEMS,
    TARGET_SE,
    ItemCandidate,
    select_next_item,
    should_stop_assessment,
)
from backend.app.modules.assessment.grade_rules import (
    GRADE_CUT_SCORES,
    GRADE_ORDER,
    GRADE_START_THETA,
    classify_theta_to_grade,
    get_start_theta,
)
from backend.app.modules.assessment.irt import estimate_theta_eap, probability_2pl

SPECIALIZATIONS = ["BACKEND", "FRONTEND", "QA", "DATA_ML"]

# Targets from the plan, section 6.3
TARGET_CORRELATION = 0.90
TARGET_ACCURACY = 0.85
TARGET_WITHIN_ONE = 0.98
TARGET_KAPPA = 0.75
TARGET_MAX_EXPOSURE = 0.25
TARGET_LENGTH = (15, 20)
MAX_ACCURACY_DROP_UNDER_NOISE = 0.05

# Population: grade shares and spread around the centre of each grade band
GRADE_MIX = {"INTERN": 0.15, "JUNIOR": 0.35, "MIDDLE": 0.35, "SENIOR": 0.15}
THETA_SD_WITHIN_GRADE = 0.5
# Self-assessment noise, same as the synthetic data generator: 75% accurate, 15% over, 10% under
SELF_ASSESSMENT = [(0, 0.75), (1, 0.15), (-1, 0.10)]

# Angoff anchors for family difficulty by target grade (plan, 4.3)
GRADE_ANCHOR_B = {"INTERN": -1.5, "JUNIOR": -0.5, "MIDDLE": 0.5, "SENIOR": 1.5}

ZERO_KNOWLEDGE_TRIALS = 300
GRADES_HIGH_TO_LOW = ["SENIOR", "MIDDLE", "JUNIOR", "INTERN"]

SWEEP_SIZES = [15, 25, 50, 100]
SWEEP_DISCRIMINATIONS = [1.0, 1.5]
# Longer tests on the largest bank: what length the accuracy and retest targets need
SWEEP_LENGTH_CAPS = [35, 45]


# ==========================================
# Bank and population
# ==========================================

@dataclass
class SimItem:
    """An item as the engine sees it, plus the parameters that actually generate responses."""
    engine: ItemCandidate
    true_a: float
    true_b: float


Bank = dict[str, list[SimItem]]


def build_real_bank(rng: np.random.Generator, b_noise_sd: float = 0.0, true_a: float | None = None) -> Bank:
    """Current registry bank. Optionally the true parameters deviate from the registered ones."""
    bank: Bank = {spec: [] for spec in SPECIALIZATIONS}
    for f in list_all_families():
        if f.specialization not in bank:
            continue
        engine = ItemCandidate(
            id=f.code, code=f.code, specialization=f.specialization, target_grade=f.target_grade,
            topic=f.topic, discrimination_a=f.discrimination_a, difficulty_b=f.difficulty_b,
        )
        bank[f.specialization].append(SimItem(
            engine=engine,
            true_a=f.discrimination_a if true_a is None else true_a,
            true_b=f.difficulty_b + (float(rng.normal(0.0, b_noise_sd)) if b_noise_sd else 0.0),
        ))
    return bank


def build_synthetic_bank(spec: str, size: int, a: float, rng: random.Random) -> Bank:
    """Calibrated synthetic bank: families spread over grades like the real one, topics per blueprint."""
    topics = BLUEPRINTS[spec]
    items = []
    for i in range(size):
        grade = GRADE_ORDER[i % len(GRADE_ORDER)]
        b = GRADE_ANCHOR_B[grade] + rng.uniform(-0.5, 0.5)
        code = f"SYN_{spec}_{i:03d}"
        engine = ItemCandidate(
            id=code, code=code, specialization=spec, target_grade=grade,
            topic=topics[i % len(topics)], discrimination_a=a, difficulty_b=b,
        )
        items.append(SimItem(engine=engine, true_a=a, true_b=b))
    return {spec: items}


@dataclass
class Candidate:
    spec: str
    true_theta: float
    true_grade: str
    declared_grade: str


def sample_population(n: int, specs: list[str], rng: random.Random, np_rng: np.random.Generator) -> list[Candidate]:
    population = []
    grades, weights = zip(*GRADE_MIX.items())
    shifts, shift_weights = zip(*SELF_ASSESSMENT)
    for i in range(n):
        grade = rng.choices(grades, weights=weights)[0]
        theta = float(np.clip(np_rng.normal(GRADE_START_THETA[grade], THETA_SD_WITHIN_GRADE), -3.0, 3.5))
        true_grade = classify_theta_to_grade(theta)
        idx = GRADE_ORDER.index(true_grade) + rng.choices(shifts, weights=shift_weights)[0]
        declared = GRADE_ORDER[min(max(idx, 0), len(GRADE_ORDER) - 1)]
        population.append(Candidate(specs[i % len(specs)], theta, true_grade, declared))
    return population


# ==========================================
# Sessions
# ==========================================

@dataclass
class SessionResult:
    theta: float
    se: float
    n_items: int
    stop_reason: str
    family_ids: set[str] = field(default_factory=set)


class CATSimulation:
    """Runs sessions against one bank, keeping exposure counters across sessions."""

    def __init__(self, bank: Bank, seed: int, max_items: int = MAX_ITEMS):
        self.rng = random.Random(seed)
        self.max_items = max_items
        self.bank = bank
        self.truth = {it.engine.id: (it.true_a, it.true_b) for items in bank.values() for it in items}
        self.pools = {spec: [it.engine for it in items] for spec, items in bank.items()}
        self.sessions_by_spec: Counter[str] = Counter()

    def run_session(self, cand: Candidate, history: set[str]) -> SessionResult:
        spec = cand.spec
        self.sessions_by_spec[spec] += 1
        theta, se = get_start_theta(cand.declared_grade), 1.0
        administered: set[str] = set()
        topics: list[str] = []
        responses: list[int] = []
        params: list[tuple[float, float]] = []

        while True:
            stop, reason = should_stop_assessment(items_count=len(responses), current_se=se, max_items=self.max_items)
            if stop:
                break
            chosen = select_next_item(
                pool=self.pools[spec],
                current_theta=theta,
                administered_item_ids=administered,
                administered_topics=topics,
                specialization=spec,
                history_item_ids=history,
                spec_session_count=self.sessions_by_spec[spec],
                rng=self.rng,
            )
            if chosen is None:
                reason = "ITEM_BANK_EXHAUSTED"
                break
            administered.add(chosen.id)
            topics.append(chosen.topic)
            chosen.exposure_count += 1

            a_true, b_true = self.truth[chosen.id]
            p = float(probability_2pl(cand.true_theta, a_true, b_true))
            responses.append(1 if self.rng.random() < p else 0)
            params.append((chosen.discrimination_a, chosen.difficulty_b))
            theta, se = estimate_theta_eap(responses, params)

        return SessionResult(theta, se, len(responses), reason, administered)

    def exposure_by_spec(self) -> dict[str, dict[str, float]]:
        return {
            spec: {
                it.code: it.exposure_count / self.sessions_by_spec[spec]
                for it in pool
            }
            for spec, pool in self.pools.items()
            if self.sessions_by_spec[spec]
        }


def run_scenario(bank: Bank, population: list[Candidate], seed: int,
                 max_items: int = MAX_ITEMS) -> tuple[list[SessionResult], list[SessionResult], CATSimulation]:
    sim = CATSimulation(bank, seed, max_items)
    first = [sim.run_session(c, history=set()) for c in population]
    retake = [sim.run_session(c, history=r.family_ids) for c, r in zip(population, first)]
    return first, retake, sim


# ==========================================
# Metrics
# ==========================================

def cohens_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    cats = sorted(set(a) | set(b))
    idx = {c: i for i, c in enumerate(cats)}
    conf = np.zeros((len(cats), len(cats)))
    for x, y in zip(a, b):
        conf[idx[x], idx[y]] += 1
    p_o = np.trace(conf) / n
    p_e = float(np.sum(conf.sum(axis=1) / n * conf.sum(axis=0) / n))
    return 1.0 if 1.0 - p_e < 1e-9 else float((p_o - p_e) / (1.0 - p_e))


def compute_metrics(population: list[Candidate], first: list[SessionResult], retake: list[SessionResult],
                    sim: CATSimulation) -> dict[str, Any]:
    true_theta = np.array([c.true_theta for c in population])
    est = np.array([r.theta for r in first])
    est_grades = [classify_theta_to_grade(r.theta) for r in first]
    retake_grades = [classify_theta_to_grade(r.theta) for r in retake]
    rank = {g: i for i, g in enumerate(GRADE_ORDER)}
    grade_gap = [abs(rank[e] - rank[c.true_grade]) for e, c in zip(est_grades, population)]

    # Decision on the declared grade: confirmed by the engine vs. should be confirmed
    pred = np.array([r.theta >= GRADE_CUT_SCORES[c.declared_grade] for r, c in zip(first, population)])
    truth = np.array([c.true_theta >= GRADE_CUT_SCORES[c.declared_grade] for c in population])

    overlaps = [len(r2.family_ids & r1.family_ids) / max(1, r2.n_items) for r1, r2 in zip(first, retake)]
    exposure = sim.exposure_by_spec()
    all_rates = [rate for rates in exposure.values() for rate in rates.values()]
    lengths = np.array([r.n_items for r in first])

    return {
        "n_candidates": len(population),
        "theta_correlation": float(pearsonr(true_theta, est)[0]),
        "theta_rmse": float(np.sqrt(np.mean((est - true_theta) ** 2))),
        "theta_bias": float(np.mean(est - true_theta)),
        "grade_accuracy": float(np.mean([g == 0 for g in grade_gap])),
        "grade_within_one": float(np.mean([g <= 1 for g in grade_gap])),
        "declared_decision_accuracy": float(np.mean(pred == truth)),
        "false_confirm_rate": float(np.mean(pred & ~truth)),
        "false_reject_rate": float(np.mean(~pred & truth)),
        "retest_kappa": cohens_kappa(est_grades, retake_grades),
        "retest_theta_correlation": float(pearsonr(est, [r.theta for r in retake])[0]),
        "retest_sessions_reusing_families": float(np.mean([o > 0 for o in overlaps])),
        "retest_mean_reused_share": float(np.mean(overlaps)),
        "max_exposure": float(max(all_rates)),
        "mean_exposure": float(np.mean(all_rates)),
        "mean_test_length": float(lengths.mean()),
        "share_max_length": float(np.mean(lengths >= sim.max_items)),
        "share_bank_exhausted": float(np.mean([r.stop_reason == "ITEM_BANK_EXHAUSTED" for r in first])),
        "share_target_se_reached": float(np.mean([r.se < TARGET_SE for r in first])),
        "mean_se": float(np.mean([r.se for r in first])),
        "bank_size": {spec: len(items) for spec, items in sim.bank.items()},
        "max_exposure_by_spec": {spec: float(max(rates.values())) for spec, rates in exposure.items()},
    }


def per_spec_metrics(population: list[Candidate], first: list[SessionResult], retake: list[SessionResult],
                     sim: CATSimulation) -> dict[str, dict[str, Any]]:
    out = {}
    exposure = sim.exposure_by_spec()
    for spec in sim.bank:
        idx = [i for i, c in enumerate(population) if c.spec == spec]
        if not idx:
            continue
        g1 = [classify_theta_to_grade(first[i].theta) for i in idx]
        g2 = [classify_theta_to_grade(retake[i].theta) for i in idx]
        out[spec] = {
            "bank_size": len(sim.bank[spec]),
            "theta_correlation": float(pearsonr([population[i].true_theta for i in idx], [first[i].theta for i in idx])[0]),
            "grade_accuracy": float(np.mean([g == population[i].true_grade for g, i in zip(g1, idx)])),
            "retest_kappa": cohens_kappa(g1, g2),
            "max_exposure": float(max(exposure[spec].values())),
            "mean_test_length": float(np.mean([first[i].n_items for i in idx])),
            "mean_se": float(np.mean([first[i].se for i in idx])),
        }
    return out


def check_targets(m: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lo, hi = TARGET_LENGTH
    checks = {
        "theta_correlation": (m["theta_correlation"], f">= {TARGET_CORRELATION}", m["theta_correlation"] >= TARGET_CORRELATION),
        "grade_accuracy": (m["grade_accuracy"], f">= {TARGET_ACCURACY:.0%}", m["grade_accuracy"] >= TARGET_ACCURACY),
        "grade_within_one": (m["grade_within_one"], f">= {TARGET_WITHIN_ONE:.0%}", m["grade_within_one"] >= TARGET_WITHIN_ONE),
        "retest_kappa": (m["retest_kappa"], f">= {TARGET_KAPPA}", m["retest_kappa"] >= TARGET_KAPPA),
        "max_exposure": (m["max_exposure"], f"<= {TARGET_MAX_EXPOSURE:.0%}", m["max_exposure"] <= TARGET_MAX_EXPOSURE),
        "mean_test_length": (m["mean_test_length"], f"{lo}–{hi}", lo <= m["mean_test_length"] <= hi),
    }
    return {k: {"value": round(v, 4), "target": t, "passed": bool(ok)} for k, (v, t, ok) in checks.items()}


# ==========================================
# Runner and report
# ==========================================

def run_sweep(n: int, seed: int) -> list[dict[str, Any]]:
    spec = "BACKEND"
    runs = [(a, size, MAX_ITEMS) for a in SWEEP_DISCRIMINATIONS for size in SWEEP_SIZES]
    runs += [(a, SWEEP_SIZES[-1], cap) for a in SWEEP_DISCRIMINATIONS for cap in SWEEP_LENGTH_CAPS]
    rows = []
    for a, size, cap in runs:
        bank = build_synthetic_bank(spec, size, a, random.Random(seed + size))
        population = sample_population(n, [spec], random.Random(seed), np.random.default_rng(seed))
        first, retake, sim = run_scenario(bank, population, seed, max_items=cap)
        m = compute_metrics(population, first, retake, sim)
        rows.append({"bank_size": size, "a": a, "max_items": cap, **{k: m[k] for k in (
            "grade_accuracy", "grade_within_one", "declared_decision_accuracy", "retest_kappa", "max_exposure",
            "mean_test_length", "share_max_length", "mean_se", "retest_sessions_reusing_families",
        )}})
        print(f"  sweep a={a:.1f} size={size:>3} cap={cap}: accuracy {m['grade_accuracy']:.1%}, "
              f"decision {m['declared_decision_accuracy']:.1%}, kappa {m['retest_kappa']:.3f}, "
              f"max exposure {m['max_exposure']:.1%}, length {m['mean_test_length']:.1f}")
    return rows


def zero_knowledge_strategies(seed: int, trials: int = ZERO_KNOWLEDGE_TRIALS) -> dict[str, Any]:
    """Grades that answering by the form of the options would confirm, per specialization.

    Every specialization's bank is shorter than the minimum test length, so a session administers every family:
    the theta of a strategy is the EAP estimate over all its families. The grade is the highest one whose
    cut-score the estimate reaches, i.e. what the candidate would get confirmed by claiming it.
    """
    rng = random.Random(seed)
    strategies = {
        "longest": lambda it: max(it.options, key=lambda k: (len(it.options[k]), rng.random())),
        "shortest": lambda it: min(it.options, key=lambda k: (len(it.options[k]), rng.random())),
        "random": lambda it: rng.choice(list(it.options)),
    }
    families = list_all_families()
    result: dict[str, Any] = {}
    for spec in SPECIALIZATIONS:
        own = [f for f in families if f.specialization == spec]
        params = [(f.discrimination_a, f.difficulty_b) for f in own]
        result[spec] = {}
        for name, pick in strategies.items():
            thetas, grades = [], Counter()
            for _ in range(trials):
                items = [GENERATORS[f.code](rng.randint(0, 10**6)) for f in own]
                theta, _ = estimate_theta_eap([int(pick(it) == it.correct_answer) for it in items], params)
                thetas.append(theta)
                grades[next((g for g in GRADES_HIGH_TO_LOW if theta >= GRADE_CUT_SCORES[g]), "NONE")] += 1
            result[spec][name] = {
                "mean_theta": float(np.mean(thetas)),
                "grade_shares": {g: grades[g] / trials for g in GRADES_HIGH_TO_LOW + ["NONE"]},
            }
    return result


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_markdown(report: dict[str, Any]) -> str:
    sc = report["scenarios"]
    real = sc["real"]["metrics"]
    lines = [
        "# Валидация механики тестирования: симуляция CAT",
        "",
        f"Сгенерировано `ml/validation/cat_sim.py` (seed {report['seed']}, {report['n_candidates']} кандидатов, "
        "по две сессии на кандидата). Цифры воспроизводятся командой `make validate`.",
        "",
        "Каждая специализация тестируется только своими семействами. Заявленный грейд содержит ошибку "
        "самооценки (75 % точно, 15 % завышают, 10 % занижают); пересдача избегает семейств первой попытки.",
        "",
        "## Текущий банк против целей плана (раздел 6.3)",
        "",
        "| Метрика | Значение | Цель | Статус |",
        "|---|---|---|---|",
    ]
    names = {
        "theta_correlation": "Корреляция θ̂ с истинной θ",
        "grade_accuracy": "Точность грейда",
        "grade_within_one": "Точность грейда ±1",
        "retest_kappa": "Согласованность пересдачи (κ Коэна)",
        "max_exposure": "Максимальная экспозиция семейства",
        "mean_test_length": "Средняя длина теста",
    }
    for key, chk in sc["real"]["targets"].items():
        v = chk["value"]
        shown = f"{v:.1f}" if key == "mean_test_length" else (f"{v:.3f}" if key in ("theta_correlation", "retest_kappa") else pct(v))
        lines.append(f"| {names[key]} | {shown} | {chk['target']} | {'✅' if chk['passed'] else '❌'} |")

    lines += [
        "",
        "Дополнительно:",
        f"- решение по заявленному грейду верно в {pct(real['declared_decision_accuracy'])} случаев; "
        f"ложное подтверждение {pct(real['false_confirm_rate'])}, ложный отказ {pct(real['false_reject_rate'])};",
        f"- RMSE θ = {real['theta_rmse']:.3f}, смещение {real['theta_bias']:+.3f}, средняя SE {real['mean_se']:.3f}, "
        f"SE < {TARGET_SE} достигнута в {pct(real['share_target_se_reached'])} сессий;",
        f"- банк исчерпан до правила остановки в {pct(real['share_bank_exhausted'])} сессий;",
        f"- при пересдаче семейства первой попытки повторно показаны в {pct(real['retest_sessions_reusing_families'])} "
        f"сессий (в среднем {pct(real['retest_mean_reused_share'])} заданий пересдачи).",
        "",
        "### По специализациям",
        "",
        "| Специализация | Семейств | r(θ̂, θ) | Точность грейда | κ пересдачи | Макс. экспозиция | Длина | Средняя SE |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for spec, m in sc["real"]["per_spec"].items():
        lines.append(f"| {spec} | {m['bank_size']} | {m['theta_correlation']:.3f} | {pct(m['grade_accuracy'])} | "
                     f"{m['retest_kappa']:.3f} | {pct(m['max_exposure'])} | {m['mean_test_length']:.1f} | {m['mean_se']:.3f} |")

    if report.get("zero_knowledge"):
        lines += [
            "",
            "## Ответы без знаний",
            "",
            "Кандидат ничего не знает и выбирает вариант по форме: самый длинный, самый короткий или наугад. "
            "Ответы даются на настоящие экземпляры заданий; банк каждой специализации короче минимальной длины теста, "
            f"поэтому сессия показывает все семейства. {ZERO_KNOWLEDGE_TRIALS} попыток на стратегию; "
            "грейд — самый высокий, порог которого достигает оценка θ̂, то есть тот, что подтвердится при заявке на него.",
            "",
            "| Специализация | Стратегия | Средняя θ̂ | Senior | Middle | Junior | Стажёр | Ниже порога Стажёра |",
            "|---|---|---|---|---|---|---|---|",
        ]
        strategy_names = {"longest": "самый длинный", "shortest": "самый короткий", "random": "наугад"}
        for spec, by_strategy in report["zero_knowledge"].items():
            for name, row in by_strategy.items():
                shares = row["grade_shares"]
                lines.append(f"| {spec} | {strategy_names[name]} | {row['mean_theta']:+.2f} | "
                             + " | ".join(pct(shares[g]) for g in GRADES_HIGH_TO_LOW + ["NONE"]) + " |")
        lines += [
            "",
            "Выбор по длине варианта не даёт преимущества перед угадыванием: варианты одного задания однотипны, "
            "а `make bank-check` не пропускает семейство, где правильный ответ слишком часто самый длинный, самый "
            "короткий или единственный повторяет число из условия. Ограничение модели: 2PL не учитывает угадывание, "
            "поэтому случайные ответы на задания с четырьмя вариантами часто дотягивают до порога Стажёра.",
        ]

    lines += [
        "",
        "## Устойчивость к ошибкам калибровки",
        "",
        "| Сценарий | Точность грейда | κ пересдачи | r(θ̂, θ) |",
        "|---|---|---|---|",
    ]
    labels = {
        "real": "Параметры банка верны",
        "real_b_noise": "Истинные b отличаются на N(0; 0,3)",
        "real_true_a1": "Истинная дискриминативность a = 1,0 (оценки a завышены)",
    }
    for key, label in labels.items():
        m = sc[key]["metrics"]
        lines.append(f"| {label} | {pct(m['grade_accuracy'])} | {m['retest_kappa']:.3f} | {m['theta_correlation']:.3f} |")
    drop = real["grade_accuracy"] - sc["real_b_noise"]["metrics"]["grade_accuracy"]
    lines += [
        "",
        f"Падение точности грейда при шуме в b: {drop * 100:.1f} п. п. "
        f"(допустимо до {MAX_ACCURACY_DROP_UNDER_NOISE * 100:.0f} п. п.).",
    ]

    if report.get("sweep"):
        lines += [
            "",
            "## Сколько семейств нужно специализации",
            "",
            "Синтетический откалиброванный банк одной специализации, сложности распределены по грейдам как в реальном банке. "
            f"{report['sweep_n']} кандидатов на прогон: разброс долей около ±2 п. п., κ — около ±0,04.",
            "",
            "| a | Семейств | Лимит заданий | Точность грейда | ±1 | Решение по заявленному | κ пересдачи | Макс. экспозиция | Длина | Упёрлись в лимит |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in report["sweep"]:
            lines.append(f"| {row['a']:.1f} | {row['bank_size']} | {row['max_items']} | {pct(row['grade_accuracy'])} | "
                         f"{pct(row['grade_within_one'])} | {pct(row['declared_decision_accuracy'])} | {row['retest_kappa']:.3f} | "
                         f"{pct(row['max_exposure'])} | {row['mean_test_length']:.1f} | {pct(row['share_max_length'])} |")
        lines += [
            "",
            "Средняя экспозиция семейства не может быть ниже «длина теста / размер банка»: при тесте "
            "из 12–25 заданий цель ≤ 25 % требует порядка 50–100 семейств на специализацию.",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--n", type=int, default=1000, help="candidates in the main scenarios")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--sweep-n", type=int, default=600, help="candidates per bank-size sweep run")
    parser.add_argument("--skip-sweep", action="store_true")
    parser.add_argument("--strict", action="store_true", help="exit 1 if the current bank misses a target")
    args = parser.parse_args()

    t0 = time.time()
    population = sample_population(args.n, SPECIALIZATIONS, random.Random(args.seed), np.random.default_rng(args.seed))
    banks = {
        "real": build_real_bank(np.random.default_rng(args.seed)),
        "real_b_noise": build_real_bank(np.random.default_rng(args.seed), b_noise_sd=0.3),
        "real_true_a1": build_real_bank(np.random.default_rng(args.seed), true_a=1.0),
    }
    scenarios: dict[str, Any] = {}
    for name, bank in banks.items():
        print(f"[CAT-SIM] scenario {name}...")
        first, retake, sim = run_scenario(bank, population, args.seed)
        metrics = compute_metrics(population, first, retake, sim)
        scenarios[name] = {"metrics": metrics, "targets": check_targets(metrics)}
        if name == "real":
            scenarios[name]["per_spec"] = per_spec_metrics(population, first, retake, sim)

    sweep = [] if args.skip_sweep else run_sweep(args.sweep_n, args.seed)
    print("[CAT-SIM] zero-knowledge strategies...")
    zero_knowledge = zero_knowledge_strategies(args.seed)

    report = {
        "seed": args.seed,
        "n_candidates": args.n,
        "elapsed_seconds": round(time.time() - t0, 1),
        "scenarios": scenarios,
        "sweep": sweep,
        "sweep_n": args.sweep_n,
        "zero_knowledge": zero_knowledge,
    }
    real_targets = scenarios["real"]["targets"]
    report["current_bank_meets_targets"] = all(t["passed"] for t in real_targets.values())

    json_path = os.path.join(CURRENT_DIR, "cat_sim_report.json")
    md_path = os.path.join(CURRENT_DIR, "cat_sim_report.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))

    print("\nCurrent bank against plan targets:")
    for key, chk in real_targets.items():
        print(f"  {key:<20} {chk['value']:>8.3f}  target {chk['target']:<8} {'PASS' if chk['passed'] else 'FAIL'}")
    print(f"\nReports: {json_path}\n         {md_path}  ({report['elapsed_seconds']}s)")

    if args.strict and not report["current_bank_meets_targets"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
