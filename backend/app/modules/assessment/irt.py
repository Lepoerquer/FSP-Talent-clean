"""2PL Item Response Theory (IRT) and Psychometric Engine.

Formulas:
- 2PL Probability: P(theta, a, b) = 1 / (1 + exp(-a * (theta - b)))
- Item Fisher Information: I(theta, a, b) = a^2 * P * (1 - P)
- Test Information: sum(I(theta, a_i, b_i))
- EAP (Expected A Posteriori) theta estimation with N(0, 1) prior via numerical quadrature
- Standard Error: posterior SD for EAP; 1 / sqrt(sum(I) + 1 / sigma_prior^2) as the information-based approximation
"""

import numpy as np
from scipy.special import expit


def probability_2pl(
    theta: float | np.ndarray,
    a: float,
    b: float,
) -> float | np.ndarray:
    """Calculate probability of correct response under 2PL IRT model.

    P(theta, a, b) = 1 / (1 + exp(-a * (theta - b)))
    Using scipy.special.expit for numerical stability.

    Args:
        theta: Candidate latent ability (scalar or array).
        a: Discrimination parameter (a >= 0.5).
        b: Difficulty parameter (-3.0 <= b <= 3.0).

    Returns:
        Probability P in range (0, 1).
    """
    z = a * (theta - b)
    return expit(z)


def fisher_information(
    theta: float | np.ndarray,
    a: float,
    b: float,
) -> float | np.ndarray:
    """Calculate Fisher information for a single item under 2PL IRT model.

    I(theta, a, b) = a^2 * P * (1 - P)

    Args:
        theta: Latent ability value.
        a: Discrimination parameter.
        b: Difficulty parameter.

    Returns:
        Information value I(theta) >= 0.
    """
    p = probability_2pl(theta, a, b)
    return (a ** 2) * p * (1.0 - p)


def total_fisher_information(
    theta: float,
    item_params: list[tuple[float, float]],
) -> float:
    """Calculate total test Fisher information across a set of items.

    I_total(theta) = sum_{i=1}^n I(theta, a_i, b_i)

    Args:
        theta: Latent ability.
        item_params: List of (a, b) parameters for administered items.

    Returns:
        Total Fisher information.
    """
    if not item_params:
        return 0.0
    info_sum = 0.0
    for a, b in item_params:
        info_sum += float(fisher_information(theta, a, b))
    return info_sum


def standard_error(
    theta: float,
    item_params: list[tuple[float, float]],
    sigma_prior: float = 1.0,
) -> float:
    """Calculate Standard Error of the ability estimate.

    SE(theta) = 1 / sqrt(sum(I) + 1 / sigma_prior^2)

    Args:
        theta: Latent ability value.
        item_params: List of (a, b) parameters of administered items.
        sigma_prior: Standard deviation of prior distribution (default 1.0 for N(0, 1)).

    Returns:
        Standard error (SE) >= 0.
    """
    prior_precision = 1.0 / (sigma_prior ** 2)
    info = total_fisher_information(theta, item_params)
    total_precision = info + prior_precision
    if total_precision <= 1e-9:
        return sigma_prior
    return float(1.0 / np.sqrt(total_precision))


def estimate_theta_eap(
    responses: list[int],
    item_params: list[tuple[float, float]],
    prior_mean: float = 0.0,
    prior_sd: float = 1.0,
    num_quad_points: int = 81,
    quad_range: tuple[float, float] = (-4.0, 4.0),
) -> tuple[float, float]:
    """Estimate latent ability theta using EAP (Expected A Posteriori) with N(0, 1) prior.

    Uses numerical grid quadrature over [quad_range[0], quad_range[1]].
    Likelihood is calculated in log-space for numerical precision.

    Args:
        responses: List of binary item responses (0 for incorrect, 1 for correct).
        item_params: List of (a, b) parameters corresponding to responses.
        prior_mean: Prior mean mu (default 0.0).
        prior_sd: Prior standard deviation sigma (default 1.0).
        num_quad_points: Number of quadrature evaluation points (default 81).
        quad_range: Min and max bounds for quadrature grid (default (-4.0, 4.0)).

    Returns:
        Tuple of (theta_eap, se_theta).
    """
    if len(responses) == 0 or len(item_params) == 0:
        return float(prior_mean), float(prior_sd)

    if len(responses) != len(item_params):
        raise ValueError(
            f"Length mismatch: {len(responses)} responses vs {len(item_params)} item params."
        )

    # 1. Define quadrature nodes and prior log-density
    q_nodes = np.linspace(quad_range[0], quad_range[1], num_quad_points)
    log_prior = -0.5 * np.log(2.0 * np.pi * (prior_sd ** 2)) - (
        (q_nodes - prior_mean) ** 2
    ) / (2.0 * (prior_sd ** 2))

    # 2. Accumulate log-likelihood across administered items
    log_likelihood = np.zeros_like(q_nodes)
    for u, (a, b) in zip(responses, item_params):
        p = probability_2pl(q_nodes, a, b)
        # Avoid log(0)
        p = np.clip(p, 1e-12, 1.0 - 1e-12)
        if u == 1:
            log_likelihood += np.log(p)
        else:
            log_likelihood += np.log(1.0 - p)

    # 3. Posterior log-density and stable exponentiation
    log_posterior = log_likelihood + log_prior
    max_log_post = np.max(log_posterior)
    unnormalized_weights = np.exp(log_posterior - max_log_post)
    norm_const = np.sum(unnormalized_weights)

    if norm_const <= 1e-15:
        # Fallback if numerical underflow
        return float(prior_mean), float(prior_sd)

    weights = unnormalized_weights / norm_const

    # 4. Compute EAP theta estimate
    theta_eap = float(np.sum(q_nodes * weights))

    # 5. SE of an EAP estimate is the posterior standard deviation (Bock & Mislevy, 1982)
    se = float(np.sqrt(np.sum(weights * (q_nodes - theta_eap) ** 2)))

    return theta_eap, se


def calculate_category_percentile(theta: float) -> int:
    """Calculate population percentile rank (1..99) for a given theta under N(0, 1).

    Args:
        theta: Estimated ability.

    Returns:
        Integer percentile in range [1, 99].
    """
    from scipy.stats import norm
    percentile = int(np.round(norm.cdf(theta) * 100))
    return max(1, min(99, percentile))


TOPIC_LEVEL_MARGIN = 0.2


def topic_profile(items: list[tuple[str, float, float, bool]], theta: float) -> list[dict]:
    """Strengths and growth areas by topic for the result screen (plan 4.2).

    items: (topic, a, b, is_correct) of the answered items. For each topic the observed number of
    correct answers is compared with the number the 2PL model expects at the final theta, so a topic
    counts as a strength only relative to the candidate's own level. With 2-4 items per topic this is a
    hint, not a measurement; the item count is returned for the UI to show.
    """
    by_topic: dict[str, list[tuple[float, float, bool]]] = {}
    for topic, a, b, correct in items:
        by_topic.setdefault(topic, []).append((a, b, correct))
    profile = []
    for topic, answers in by_topic.items():
        expected = float(sum(probability_2pl(theta, a, b) for a, b, _ in answers))
        correct = sum(1 for _, _, ok in answers if ok)
        gap = (correct - expected) / len(answers)
        level = "STRONG" if gap >= TOPIC_LEVEL_MARGIN else ("GROWTH" if gap <= -TOPIC_LEVEL_MARGIN else "ON_LEVEL")
        profile.append({"topic": topic, "items": len(answers), "correct": correct,
                        "expected": round(expected, 2), "level": level})
    return sorted(profile, key=lambda t: (t["correct"] - t["expected"]) / t["items"], reverse=True)
