"""Evaluation of the need / vacancy text parser (R2-07) against gold structures.

Gold: ml/data/need_parsing_gold.json. "dev" items (the reference needs) may be inspected while
developing the parser; "holdout" items were written before it and are reported separately.
Add more texts (e.g. from Р4) to the gold file, ideally as "holdout".

Usage:
  python ml/validation/need_parsing_eval.py
"""

import json
import os
import sys
from typing import Any

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.modules.matching.need_parser import ParsedNeed, parse_need

GOLD_PATH = os.path.join(PROJECT_ROOT, "ml", "data", "need_parsing_gold.json")
REFERENCE_PATH = os.path.join(PROJECT_ROOT, "ml", "data", "reference_needs.json")
FIELDS = ["specialization", "grade", "work_format", "city", "salary_from", "salary_to", "experience_years"]
CORE_FIELDS = ["specialization", "grade", "work_format", "city"]
# Holdout before any change motivated by it, and the changes made after that run
HOLDOUT_FIRST_RUN = {
    "fields_all_correct": 1.0,
    "skills": {"precision": 0.89, "recall": 1.00, "f1": 0.94},
    "fixes_after": "синоним «руби» (Ruby) после обрезки окончания совпадал с «руб.» — короткие основы больше не обрезаются; "
                   "в стоп-лист добавлены бытовые синонимы («чарты», «графики», «блок», «вектор», «провайдер» и др.)",
}
FIELD_RU = {
    "specialization": "Специализация", "grade": "Грейд", "work_format": "Формат", "city": "Город",
    "salary_from": "Зарплата от", "salary_to": "Зарплата до", "experience_years": "Опыт, лет",
}


def load_gold() -> list[dict[str, Any]]:
    with open(GOLD_PATH, encoding="utf-8") as f:
        gold = json.load(f)["items"]
    with open(REFERENCE_PATH, encoding="utf-8") as f:
        reference = json.load(f)
    for item in gold:
        if "reference" in item:
            ref = reference[item["reference"]]
            item["title"], item["text"] = ref["title"], ref["raw_description"]
    return gold


def predicted_fields(parsed: ParsedNeed) -> dict[str, Any]:
    return {
        "specialization": parsed.specialization.value,
        "grade": parsed.grade.value,
        "work_format": parsed.work_format.value,
        "city": parsed.city.value,
        "salary_from": parsed.salary_from,
        "salary_to": parsed.salary_to,
        "experience_years": parsed.experience_years,
    }


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def evaluate(items: list[dict[str, Any]]) -> dict[str, Any]:
    field_hits = dict.fromkeys(FIELDS, 0)
    counts = {"skills": [0, 0, 0], "nice_to_have": [0, 0, 0]}
    core_correct = 0
    details = []
    for item in items:
        parsed = parse_need(item["text"], item["title"])
        pred, exp = predicted_fields(parsed), item["expected"]
        wrong = {f: {"expected": exp[f], "got": pred[f]} for f in FIELDS if pred[f] != exp[f]}
        for f in FIELDS:
            field_hits[f] += f not in wrong
        core_correct += all(f not in wrong for f in CORE_FIELDS)
        diff = {}
        for key, got in (("skills", parsed.required_skill_names), ("nice_to_have", [s.name for s in parsed.nice_to_have])):
            want, have = set(exp[key]), set(got)
            tp, fp, fn = len(want & have), len(have - want), len(want - have)
            counts[key] = [counts[key][0] + tp, counts[key][1] + fp, counts[key][2] + fn]
            diff[key] = {"extra": sorted(have - want), "missed": sorted(want - have)}
        details.append({"id": item["id"], "title": item["title"], "wrong_fields": wrong, **diff,
                        "evidence": {"specialization": parsed.specialization.evidence, "grade": parsed.grade.evidence}})
    n = len(items)
    return {
        "items": n,
        "field_accuracy": {f: field_hits[f] / n for f in FIELDS},
        "core_fields_all_correct": core_correct / n,
        "skills": prf(*counts["skills"]),
        "nice_to_have": prf(*counts["nice_to_have"]),
        "details": details,
    }


def render_markdown(results: dict[str, dict[str, Any]]) -> str:
    sets = list(results)
    lines = [
        "# Разбор текста вакансии в структуру (R2-07)",
        "",
        "Сгенерировано `ml/validation/need_parsing_eval.py` по эталону `ml/data/need_parsing_gold.json`. "
        "Dev — тексты из `reference_needs.json`, на них разбор отлаживался; holdout написаны до разбора и "
        "под них не подгонялись (но тем же автором, поэтому настоящая проверка — тексты Р4).",
        "",
        "| Поле | " + " | ".join(f"{s} ({results[s]['items']})" for s in sets) + " |",
        "|---|" + "---|" * len(sets),
    ]
    for f in FIELDS:
        lines.append(f"| {FIELD_RU[f]} | " + " | ".join(f"{results[s]['field_accuracy'][f]:.0%}" for s in sets) + " |")
    lines.append("| Специализация, грейд, формат и город верны одновременно | "
                 + " | ".join(f"{results[s]['core_fields_all_correct']:.0%}" for s in sets) + " |")
    for key, label in (("skills", "Стек"), ("nice_to_have", "«Будет плюсом»")):
        lines.append(f"| {label}: precision / recall / F1 | " + " | ".join(
            f"{results[s][key]['precision']:.2f} / {results[s][key]['recall']:.2f} / {results[s][key]['f1']:.2f}" for s in sets) + " |")

    first = HOLDOUT_FIRST_RUN
    lines += [
        "",
        f"Первый прогон holdout, до любых правок по нему: все поля верны в {first['fields_all_correct']:.0%} текстов, "
        f"стек P {first['skills']['precision']:.2f} / R {first['skills']['recall']:.2f} / F1 {first['skills']['f1']:.2f}. "
        f"После него исправлено: {first['fixes_after']}. Цифры в таблице — после исправлений, поэтому holdout "
        "уже не полностью независим.",
        "",
        "## Ошибки по текстам",
        "",
    ]
    for s in sets:
        for d in results[s]["details"]:
            problems = []
            for f, v in d["wrong_fields"].items():
                problems.append(f"{FIELD_RU[f].lower()}: ожидалось {v['expected']}, получено {v['got']}")
            for key, label in (("skills", "стек"), ("nice_to_have", "плюсом")):
                if d[key]["missed"]:
                    problems.append(f"{label}, пропущено: {', '.join(d[key]['missed'])}")
                if d[key]["extra"]:
                    problems.append(f"{label}, лишнее: {', '.join(d[key]['extra'])}")
            if problems:
                lines.append(f"- **{d['id']}** «{d['title']}»: " + "; ".join(problems) + ".")
    return "\n".join(lines) + "\n"


def main() -> None:
    gold = load_gold()
    results = {s: evaluate([g for g in gold if g["set"] == s]) for s in ("dev", "holdout")}
    with open(os.path.join(CURRENT_DIR, "need_parsing_report.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(os.path.join(CURRENT_DIR, "need_parsing_report.md"), "w", encoding="utf-8") as f:
        f.write(render_markdown(results))
    for s, r in results.items():
        acc = ", ".join(f"{f} {r['field_accuracy'][f]:.0%}" for f in CORE_FIELDS)
        print(f"{s:8} items {r['items']}: {acc}; skills F1 {r['skills']['f1']:.2f}; nice F1 {r['nice_to_have']['f1']:.2f}")


if __name__ == "__main__":
    main()
