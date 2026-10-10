"""Adaptive Testing (CAT) Engine with 2PL IRT item selection and stopping rules.

Key capabilities:
- Item selection: Randomesque selection from top-5 Maximum Fisher Information items.
- Blueprint topic balancing: Dynamically balances item topics within specialization.
- Item family exposure control: Restricts exposure rate to <= 25% of sessions in the specialization.
- Candidate history exclusion: Prefers families the candidate has not seen in earlier sessions.
- Items never come from another specialization.
- Stopping rule: SE < 0.30 OR count >= 25 items (with min 12 items).
"""

import random
from dataclasses import dataclass, field

from backend.app.modules.assessment.irt import (
    fisher_information,
)


@dataclass
class ItemCandidate:
    """Item family metadata required for adaptive selection."""
    id: str
    code: str
    specialization: str
    target_grade: str
    topic: str
    discrimination_a: float
    difficulty_b: float
    exposure_count: int = 0
    is_active: bool = True


@dataclass
class CATSessionState:
    """In-memory representation of an active CAT session state."""
    session_id: str
    specialization: str
    target_grade: str
    current_theta: float = 0.0
    current_se: float = 1.0
    administered_item_ids: list[str] = field(default_factory=list)
    administered_family_codes: list[str] = field(default_factory=list)
    administered_topics: list[str] = field(default_factory=list)
    responses: list[int] = field(default_factory=list)
    item_params: list[tuple[float, float]] = field(default_factory=list)


# Topic blueprints by specialization
BLUEPRINTS: dict[str, list[str]] = {
    "BACKEND": ["Python", "SQL", "Algorithms", "HTTP_Async"],
    "FRONTEND": ["JS_TS", "React", "CSS", "DOM"],
    "QA": ["Testing_Types", "Test_Cases", "Bug_Reports", "Automation"],
    "DATA_ML": ["Metrics", "Feature_Engineering", "Models", "Data_Processing"],
}

# Stopping rule parameters
MIN_ITEMS = 12
MAX_ITEMS = 25
TARGET_SE = 0.30
MAX_EXPOSURE_RATE = 0.25
RANDOMESQUE_TOP_K = 5
# Exposure rates are meaningless over the first few sessions of a specialization
EXPOSURE_WARMUP_SESSIONS = 15

# Demo / Express mode for jury (3-5 minutes express test, exactly 5 questions)
DEMO_MIN_ITEMS = 5
DEMO_MAX_ITEMS = 5


def should_stop_assessment(
    items_count: int,
    current_se: float,
    min_items: int = MIN_ITEMS,
    max_items: int = MAX_ITEMS,
    target_se: float = TARGET_SE,
) -> tuple[bool, str]:
    """Check if CAT session should terminate according to stopping rules.

    Rules:
    1. Count must be >= min_items (12) before any SE-based stopping.
    2. If count >= min_items and SE < target_se (0.30) -> STOP.
    3. If count >= max_items (25) -> STOP.
    4. Otherwise -> CONTINUE.

    Returns:
        Tuple of (should_stop: bool, reason: str).
    """
    if items_count < min_items:
        return False, "MIN_ITEMS_NOT_REACHED"

    if current_se < target_se:
        return True, "TARGET_SE_ACHIEVED"

    if items_count >= max_items:
        return True, "MAX_ITEMS_REACHED"

    return False, "IN_PROGRESS"


def _norm(value: str) -> str:
    return value.upper().replace(" ", "_")


def filter_eligible_items(
    pool: list[ItemCandidate],
    specialization: str,
    excluded_item_ids: set[str],
    history_item_ids: set[str] | frozenset[str] = frozenset(),
    spec_session_count: int = 0,
    max_exposure_rate: float = MAX_EXPOSURE_RATE,
) -> list[ItemCandidate]:
    """Filter item candidates by activity, specialization, exclusion, and exposure limit.

    Items never leave the candidate's specialization: a Backend test is scored on
    Backend families only, otherwise theta would mix unrelated abilities.

    Args:
        pool: List of all item candidates in the bank.
        specialization: Candidate's specialization (case-insensitive).
        excluded_item_ids: IDs already administered in this session (hard exclusion).
        history_item_ids: IDs administered in the candidate's earlier sessions. They are
            avoided while unseen families remain; on a small bank a retake falls back to
            them (rendered with a fresh seed) instead of ending early.
        spec_session_count: Number of sessions in this specialization, the denominator
            of the exposure rate.
        max_exposure_rate: Maximum allowed exposure rate (0.25 = 25%).

    Returns:
        List of eligible items.
    """
    spec_norm = _norm(specialization)
    in_track = [
        item for item in pool
        if item.is_active
        and _norm(item.specialization) == spec_norm
        and item.id not in excluded_item_ids
    ]
    unseen = [item for item in in_track if item.id not in history_item_ids]
    candidates = unseen or in_track
    if not candidates:
        return []

    # Restricted exposure control: drop families shown in more than max_exposure_rate of
    # sessions. If too few remain, keep the least exposed ones so selection still has a choice.
    if spec_session_count >= EXPOSURE_WARMUP_SESSIONS:
        under_limit = [
            item for item in candidates
            if item.exposure_count / spec_session_count <= max_exposure_rate
        ]
        if len(under_limit) >= RANDOMESQUE_TOP_K:
            candidates = under_limit
        else:
            candidates = sorted(candidates, key=lambda it: it.exposure_count)[:RANDOMESQUE_TOP_K]

    return candidates


def apply_topic_balancing(
    candidates: list[ItemCandidate],
    administered_topics: list[str],
    blueprint_topics: list[str] | None = None,
) -> list[ItemCandidate]:
    """Balance content blueprint across topics within specialization.

    Prioritizes items belonging to topics with lowest administration count.

    Args:
        candidates: Pre-filtered eligible item candidates.
        administered_topics: Topics already administered in this session.
        blueprint_topics: Optional explicit list of topics in blueprint.

    Returns:
        Filtered or prioritized candidate list.
    """
    if not candidates:
        return []

    # Count occurrences of each topic so far
    topic_counts: dict[str, int] = {}
    for t in administered_topics:
        norm_t = t.upper().replace(" ", "_")
        topic_counts[norm_t] = topic_counts.get(norm_t, 0) + 1

    # Extract all candidate topics
    candidate_topics = {it.topic.upper().replace(" ", "_") for it in candidates}
    if blueprint_topics:
        for bt in blueprint_topics:
            norm_bt = bt.upper().replace(" ", "_")
            if norm_bt not in topic_counts:
                topic_counts[norm_bt] = 0

    # Find minimum topic count among available topics
    min_count = min(
        (topic_counts.get(t, 0) for t in candidate_topics),
        default=0,
    )

    # Prioritize items from topics with lowest count
    prioritized = [
        it for it in candidates
        if topic_counts.get(it.topic.upper().replace(" ", "_"), 0) == min_count
    ]

    # If prioritized has at least 3 candidates, use them; otherwise return all candidates
    return prioritized if len(prioritized) >= 3 else candidates


def select_next_item(
    pool: list[ItemCandidate],
    current_theta: float,
    administered_item_ids: set[str],
    administered_topics: list[str],
    specialization: str,
    history_item_ids: set[str] | frozenset[str] = frozenset(),
    spec_session_count: int = 0,
    top_k: int = RANDOMESQUE_TOP_K,
    rng: random.Random | None = None,
) -> ItemCandidate | None:
    """Select the next CAT item using Randomesque Maximum Fisher Information.

    Workflow:
    1. Filter items by specialization, active status, exposure limit (<= 25%),
       and exclusion of items already presented to this candidate.
    2. Apply blueprint topic balancing to prioritize under-represented topics.
    3. Calculate Fisher Information I(theta, a, b) for all remaining items.
    4. Rank by Fisher Information descending and take top-K (default 5).
    5. Randomly choose one item from top-K to prevent item memorization and leaks.

    Args:
        pool: Full item candidate bank.
        current_theta: Current ability estimate theta.
        administered_item_ids: Set of item IDs already presented in this session.
        administered_topics: List of topic names already presented.
        specialization: Candidate's specialization.
        history_item_ids: Item IDs from the candidate's earlier sessions (soft exclusion).
        spec_session_count: Sessions in this specialization, for exposure tracking.
        top_k: Size of the randomesque selection set (default 5).
        rng: Optional seeded random.Random instance for deterministic simulation/tests.

    Returns:
        Selected ItemCandidate, or None if no items remain.
    """
    if rng is None:
        rng = random.Random()

    # 1. Filter candidates
    eligible = filter_eligible_items(
        pool=pool,
        specialization=specialization,
        excluded_item_ids=administered_item_ids,
        history_item_ids=history_item_ids,
        spec_session_count=spec_session_count,
        max_exposure_rate=MAX_EXPOSURE_RATE,
    )

    if not eligible:
        return None

    # 2. Topic balancing
    blueprint = BLUEPRINTS.get(_norm(specialization))
    balanced = apply_topic_balancing(
        candidates=eligible,
        administered_topics=administered_topics,
        blueprint_topics=blueprint,
    )

    # 3. Compute Fisher Information at current theta
    scored_items: list[tuple[float, ItemCandidate]] = []
    for item in balanced:
        info = float(fisher_information(current_theta, item.discrimination_a, item.difficulty_b))
        scored_items.append((info, item))

    # 4. Sort descending by Fisher Information
    scored_items.sort(key=lambda pair: pair[0], reverse=True)

    # 5. Take top-K and select randomly
    top_items = [item for _, item in scored_items[:top_k]]
    return rng.choice(top_items)
