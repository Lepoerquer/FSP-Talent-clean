"""Item Bank Validator for Psychometric CAT Families.

Validates that:
1. Every family has a unique code, specialization, target grade, valid topic, and format.
2. Discrimination parameter a >= 0.5.
3. Difficulty parameter b in [-3.0, 3.0].
4. Every family generator produces >= 30 distinct question stems (text + code) across 50 seeds.
   Shuffling the options of the same question does not count as a new instance: a leaked
   answer stays valid for it.
5. No single correct answer dominates: the most frequent correct option text appears in at most
   35% of instances, so memorising "the usual answer" barely beats guessing (25% for 4 options).
6. All generated instances have distinct option texts, and the correct answer is among the options.
7. Every specialization has families on every grade. Without intern-level items the test cannot tell a weak
   candidate from an intern: answering everything wrong would still confirm the Intern grade.
8. The correct option is not given away by its form. It is the strictly longest option in at most 40% of
   instances, and the strictly shortest in at most 40% (25% is chance for 4 options); in at most 25% of instances
   it is the only option that repeats a number or a `code` token from the stem. Otherwise "pick the longest,
   most detailed option", "pick the shortest" or "pick the option that mentions the stem" answers the family
   without any knowledge.
"""

import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

# Ensure project paths are in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from families.base import ItemRenderResult
from families.registry import FAMILIES_METADATA, GENERATORS, ItemFamilyMeta

VALID_SPECIALIZATIONS = {"BACKEND", "FRONTEND", "QA", "DATA_ML"}
VALID_GRADES = {"INTERN", "JUNIOR", "MIDDLE", "SENIOR"}
VALID_FORMATS = {"CODE_OUTPUT", "CODE_ERROR", "SQL", "COMPLEXITY", "MCQ"}
MIN_DISCRIMINATION = 0.5
MIN_DIFFICULTY = -3.0
MAX_DIFFICULTY = 3.0
NUM_TEST_SEEDS = 50
MIN_UNIQUE_STEMS = 30
MAX_TOP_ANSWER_SHARE = 0.35
MAX_LONGEST_KEY_SHARE = 0.40
MAX_SHORTEST_KEY_SHARE = 0.40
MAX_STEM_ECHO_SHARE = 0.25
STEM_TOKEN = re.compile(r"\d{2,}|`[^`]+`")


class BankValidationError(Exception):
    pass


def instance_stem(res: ItemRenderResult) -> str:
    """What the candidate actually reads, independent of option order."""
    return "||".join([res.question_text.strip(), (res.code_snippet or "").strip()])


def validate_family_metadata(meta: ItemFamilyMeta) -> list[str]:
    """Validate metadata parameters of an item family."""
    errors = []
    if not meta.code or not meta.code.isidentifier():
        errors.append(f"Invalid code '{meta.code}' (must be valid identifier)")
    if meta.specialization not in VALID_SPECIALIZATIONS:
        errors.append(f"Invalid specialization '{meta.specialization}'. Valid: {VALID_SPECIALIZATIONS}")
    if meta.target_grade not in VALID_GRADES:
        errors.append(f"Invalid target_grade '{meta.target_grade}'. Valid: {VALID_GRADES}")
    if not meta.topic:
        errors.append("Topic must not be empty")
    if meta.item_format not in VALID_FORMATS:
        errors.append(f"Invalid item_format '{meta.item_format}'. Valid: {VALID_FORMATS}")
    if meta.discrimination_a < MIN_DISCRIMINATION:
        errors.append(f"Discrimination a={meta.discrimination_a} < {MIN_DISCRIMINATION}")
    if not (MIN_DIFFICULTY <= meta.difficulty_b <= MAX_DIFFICULTY):
        errors.append(f"Difficulty b={meta.difficulty_b} not in [{MIN_DIFFICULTY}, {MAX_DIFFICULTY}]")
    return errors


@dataclass
class GeneratorStats:
    unique_stems: int = 0
    top_answer_share: float = 1.0
    longest_key_share: float = 0.0
    shortest_key_share: float = 0.0
    stem_echo_share: float = 0.0
    errors: list[str] = field(default_factory=list)


def answer_cues(res: ItemRenderResult) -> tuple[bool, bool, bool]:
    """(the key is the strictly longest option, the strictly shortest, the only one repeating a stem token)."""
    key_text = res.options[res.correct_answer]
    others = [text for k, text in res.options.items() if k != res.correct_answer]
    longest = len(key_text) > max(len(text) for text in others)
    shortest = len(key_text) < min(len(text) for text in others)
    stem_tokens = set(STEM_TOKEN.findall(instance_stem(res)))

    def echoes(text: str) -> bool:
        return bool(stem_tokens & set(STEM_TOKEN.findall(text)))

    return longest, shortest, echoes(key_text) and not any(echoes(text) for text in others)


def validate_family_generator(code: str, num_seeds: int = NUM_TEST_SEEDS) -> GeneratorStats:
    """Render the family across seeds and check stem diversity and answer spread."""
    stats = GeneratorStats()
    if code not in GENERATORS:
        stats.errors.append(f"No generator registered for family '{code}'")
        return stats

    gen_func = GENERATORS[code]
    stems: set[str] = set()
    answers: Counter[str] = Counter()
    rendered = longest_count = shortest_count = echo_count = 0

    for seed in range(num_seeds):
        try:
            res: ItemRenderResult = gen_func(seed)
        except Exception as exc:
            stats.errors.append(f"Generator crashed on seed {seed}: {exc}")
            continue

        if not res.question_text:
            stats.errors.append(f"Seed {seed}: Empty question_text")
        if not res.options or len(res.options) < 2:
            stats.errors.append(f"Seed {seed}: Options dict must contain at least 2 entries")
        option_texts = [v.strip() for v in res.options.values()]
        if len(set(option_texts)) != len(option_texts):
            stats.errors.append(f"Seed {seed}: Duplicate option texts make the key ambiguous")
        if res.correct_answer not in res.options:
            stats.errors.append(
                f"Seed {seed}: Correct answer '{res.correct_answer}' not in options {list(res.options.keys())}"
            )
            continue
        if not res.explanation:
            stats.errors.append(f"Seed {seed}: Empty explanation")

        rendered += 1
        stems.add(instance_stem(res))
        answers[res.options[res.correct_answer].strip()] += 1
        longest, shortest, echo = answer_cues(res)
        longest_count += longest
        shortest_count += shortest
        echo_count += echo

    stats.unique_stems = len(stems)
    if rendered:
        stats.top_answer_share = answers.most_common(1)[0][1] / rendered
        stats.longest_key_share = longest_count / rendered
        stats.shortest_key_share = shortest_count / rendered
        stats.stem_echo_share = echo_count / rendered

    if stats.unique_stems < MIN_UNIQUE_STEMS:
        stats.errors.append(
            f"Insufficient instance diversity: {stats.unique_stems} distinct question stems "
            f"across {num_seeds} seeds (required >= {MIN_UNIQUE_STEMS}); shuffled options do not count"
        )
    if stats.top_answer_share > MAX_TOP_ANSWER_SHARE:
        stats.errors.append(
            f"Leak-prone key: the same correct answer appears in {stats.top_answer_share:.0%} of instances "
            f"(allowed <= {MAX_TOP_ANSWER_SHARE:.0%})"
        )
    if stats.longest_key_share > MAX_LONGEST_KEY_SHARE:
        stats.errors.append(
            f"Answer cue: the correct option is the longest in {stats.longest_key_share:.0%} of instances "
            f"(allowed <= {MAX_LONGEST_KEY_SHARE:.0%}); make the options parallel and move the reasoning to explanation"
        )
    if stats.shortest_key_share > MAX_SHORTEST_KEY_SHARE:
        stats.errors.append(
            f"Answer cue: the correct option is the shortest in {stats.shortest_key_share:.0%} of instances "
            f"(allowed <= {MAX_SHORTEST_KEY_SHARE:.0%})"
        )
    if stats.stem_echo_share > MAX_STEM_ECHO_SHARE:
        stats.errors.append(
            f"Answer cue: only the correct option repeats a number or token from the stem in "
            f"{stats.stem_echo_share:.0%} of instances (allowed <= {MAX_STEM_ECHO_SHARE:.0%})"
        )
    return stats


MIN_FAMILIES_PER_GRADE = 2


def grade_coverage() -> dict[str, dict[str, int]]:
    coverage = {spec: dict.fromkeys(sorted(VALID_GRADES, key=["INTERN", "JUNIOR", "MIDDLE", "SENIOR"].index), 0)
                for spec in sorted(VALID_SPECIALIZATIONS)}
    for meta in FAMILIES_METADATA.values():
        if meta.specialization in coverage and meta.target_grade in VALID_GRADES:
            coverage[meta.specialization][meta.target_grade] += 1
    return coverage


def run_full_validation() -> bool:
    """Run full validation suite on all registered item families."""
    print("=" * 140)
    print("           FSP-TALENT PSYCHOMETRIC ITEM BANK VALIDATOR (2PL IRT / CAT)")
    print("=" * 140)
    header = (
        f"{'Family Code':<30} | {'Spec':<8} | {'Topic':<19} | {'Grade':<7} | "
        f"{'a':>4} | {'b':>5} | {'Stems/50':>8} | {'TopAns':>6} | {'Long':>4} | {'Short':>5} | {'Echo':>4} | "
        f"{'Status':<6}"
    )
    print(header)
    print("-" * 140)

    all_passed = True
    total_families = len(FAMILIES_METADATA)
    passed_count = 0

    for code, meta in FAMILIES_METADATA.items():
        meta_errors = validate_family_metadata(meta)
        stats = validate_family_generator(code)
        all_errors = meta_errors + stats.errors

        if not all_errors:
            status = "PASS"
            passed_count += 1
        else:
            status = "FAIL"
            all_passed = False

        row = (
            f"{code:<30} | {meta.specialization:<8} | {meta.topic:<19} | {meta.target_grade:<7} | "
            f"{meta.discrimination_a:>4.2f} | {meta.difficulty_b:>5.2f} | {stats.unique_stems:>8} | "
            f"{stats.top_answer_share:>6.0%} | {stats.longest_key_share:>4.0%} | {stats.shortest_key_share:>5.0%} | "
            f"{stats.stem_echo_share:>4.0%} | "
            f"{status:<6}"
        )
        print(row)

        if all_errors:
            for err in all_errors:
                print(f"    --> ERROR: {err}")

    print("-" * 140)
    print(f"Grade coverage (families per target grade, at least {MIN_FAMILIES_PER_GRADE} each):")
    for spec, counts in grade_coverage().items():
        short = [g for g, n in counts.items() if n < MIN_FAMILIES_PER_GRADE]
        status = "PASS" if not short else f"FAIL (too few: {', '.join(short)})"
        print(f"  {spec:<9} " + "  ".join(f"{g} {n}" for g, n in counts.items()) + f"  {status}")
        if short:
            all_passed = False
    print("-" * 140)
    print(f"Summary: {passed_count}/{total_families} item families passed validation.")
    if all_passed:
        print("[SUCCESS] All item families conform to psychometric, uniqueness, and IRT 2PL requirements!")
    else:
        print("[FAILURE] Validation errors detected. Please review error messages above.")
    print("=" * 140)

    return all_passed


if __name__ == "__main__":
    success = run_full_validation()
    sys.exit(0 if success else 1)
