"""Base abstractions for parameterized psychometric item families."""

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

OPTION_KEYS = "ABCD"


def build_options(
    rng: random.Random,
    correct: str,
    distractors: Iterable[str],
    n_options: int = 4,
) -> tuple[dict[str, str], str]:
    """Shuffle the correct answer with the first distinct distractors.

    Distractors equal to the correct answer or to each other are skipped, so a generator
    can list typical-mistake answers first and append numeric fallbacks after them.

    Returns:
        (options keyed "A".."D", key of the correct option).
    """
    chosen = [correct]
    for text in distractors:
        if text not in chosen:
            chosen.append(text)
        if len(chosen) == n_options:
            break
    if len(chosen) < n_options:
        raise ValueError(f"Need {n_options - 1} distinct distractors, got {len(chosen) - 1}")
    rng.shuffle(chosen)
    options = {OPTION_KEYS[i]: text for i, text in enumerate(chosen)}
    return options, OPTION_KEYS[chosen.index(correct)]


@dataclass
class ItemRenderResult:
    """Rendered instance of an isomorphic item family."""
    family_code: str
    seed: int
    question_text: str
    code_snippet: str | None = None
    options: dict[str, str] = field(default_factory=dict)  # e.g. {"A": "...", "B": "...", ...}
    correct_answer: str = ""  # Key in options, e.g. "A"
    explanation: str = ""
    item_format: str = "MCQ"

    def to_client_dict(self) -> dict[str, Any]:
        """Convert to client-safe representation (hiding correct answer and explanation)."""
        return {
            "family_code": self.family_code,
            "seed": self.seed,
            "question_text": self.question_text,
            "code_snippet": self.code_snippet,
            "options": self.options,
            "item_format": self.item_format,
        }

    def to_full_dict(self) -> dict[str, Any]:
        """Convert to complete representation including validation details."""
        return {
            "family_code": self.family_code,
            "seed": self.seed,
            "question_text": self.question_text,
            "code_snippet": self.code_snippet,
            "options": self.options,
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "item_format": self.item_format,
        }


@dataclass
class ItemFamilyMeta:
    """Metadata describing an item family for IRT calibration and blueprints."""
    code: str
    specialization: str
    target_grade: str
    topic: str
    item_format: str
    discrimination_a: float
    difficulty_b: float
    description: str
    template_yaml: str | None = None
