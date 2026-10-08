"""Stage 5: human-readable reasons, generated from the feature values (B10).

Deterministic templates only. A reason is offered when its feature is clearly
strong; reasons are ordered by how much that feature contributed to the score.
"""

from .config import DEFAULT_CONFIG, RecommenderConfig
from .models import ExperienceInfo, Strategy, UserProfile

# A feature must reach these values before we mention it.
STRONG_CATEGORY = 0.75
STRONG_DIFFICULTY = 0.85
STRONG_DURATION = 0.8
STRONG_POPULARITY = 0.6
STRONG_FRESHNESS = 0.8
SHOWED_INTEREST = 0.55


def explain(
    exp: ExperienceInfo,
    features: dict[str, float],
    profile: UserProfile,
    strategy: Strategy,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> list[str]:
    weights = config.cold_start_weights if strategy == "cold_start" else config.feature_weights
    candidates: list[tuple[float, str]] = []  # (contribution to score, sentence)

    def offer(feature: str, sentence: str) -> None:
        candidates.append((weights.get(feature, 0) * features.get(feature, 0), sentence))

    if features.get("popularity", 0) >= STRONG_POPULARITY:
        offer("popularity", "popular with other L.I.V.E users")
    if features.get("freshness", 0) >= STRONG_FRESHNESS:
        offer("freshness", "recently added")

    if strategy == "cold_start":
        reasons = [s for _, s in sorted(candidates, key=lambda c: -c[0])][: config.max_reasons - 1]
        return ["a popular starting point while we learn what you like", *reasons]

    if features["category_match"] >= STRONG_CATEGORY:
        offer("category_match", f"matches your interest in {exp.category}")
    if exp.id in profile.saved:
        offer("interaction_preference", "you saved this earlier")
    elif exp.id in profile.liked:
        offer("interaction_preference", "you liked this before")
    elif features["interaction_preference"] >= SHOWED_INTEREST:
        offer("interaction_preference", "you showed interest in this before")
    if profile.preferred_difficulty is not None and features["difficulty_match"] >= STRONG_DIFFICULTY:
        offer("difficulty_match", f"at your usual difficulty ({exp.difficulty})")
    if profile.preferred_duration is not None and features["duration_match"] >= STRONG_DURATION:
        offer("duration_match", f"close to the length you usually pick (~{round(profile.preferred_duration)} min)")
    if profile.preferred_cost is not None and features["cost_match"] >= 1.0:
        offer("cost_match", "free" if exp.cost == 0 else "within your usual budget")
    if exp.category not in profile.category_affinity:
        offer("novelty", f"something new for you: {exp.category}")

    reasons = [s for _, s in sorted(candidates, key=lambda c: -c[0])][: config.max_reasons]
    return reasons or ["a balanced match across your preferences"]
