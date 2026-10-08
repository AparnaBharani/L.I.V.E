"""Stage 3: feature computation and weighted scoring (B6).

Every feature is normalised to [0, 1] so that no feature dominates just because its raw
numbers are bigger. For preference features, 0.5 (NEUTRAL) means "no information".
"""

import math
from collections.abc import Mapping
from datetime import datetime

from .config import DEFAULT_CONFIG, NEUTRAL, RecommenderConfig
from .models import ExperienceInfo, UserProfile
from .profile import recency_weight


def category_match(exp: ExperienceInfo, profile: UserProfile) -> float:
    """How the user feels about this category: affinity [-1, 1] mapped to [0, 1]."""
    affinity = profile.category_affinity.get(exp.category)
    return NEUTRAL if affinity is None else (affinity + 1) / 2


def interaction_preference(exp: ExperienceInfo, profile: UserProfile, config: RecommenderConfig) -> float:
    """The user's direct history with this exact experience (e.g. saved it, skipped it)."""
    affinity = profile.item_affinity.get(exp.id)
    if affinity is None:
        return NEUTRAL
    return (math.tanh(affinity / config.interaction_scale) + 1) / 2


def difficulty_match(exp: ExperienceInfo, profile: UserProfile, config: RecommenderConfig) -> float:
    """1 at the user's usual level, falling linearly to 0 at the far end of the scale."""
    level = config.difficulty_levels.get(exp.difficulty)
    if profile.preferred_difficulty is None or level is None:
        return NEUTRAL
    span = max(config.difficulty_levels.values()) - min(config.difficulty_levels.values())
    return 1 - abs(level - profile.preferred_difficulty) / span


def duration_match(exp: ExperienceInfo, profile: UserProfile) -> float:
    """Ratio of shorter to longer: 120 min vs a usual 60 min scores 0.5."""
    preferred = profile.preferred_duration
    if preferred is None:
        return NEUTRAL
    return min(exp.duration_minutes, preferred) / max(exp.duration_minutes, preferred)


def cost_match(exp: ExperienceInfo, profile: UserProfile, config: RecommenderConfig) -> float:
    """1 if no pricier than usual; otherwise shrinks as the price rises above it."""
    preferred = profile.preferred_cost
    if preferred is None:
        return NEUTRAL
    if exp.cost <= preferred:
        return 1.0
    s = config.cost_smoothing
    return (preferred + s) / (exp.cost + s)


def popularity(exp: ExperienceInfo, fans: Mapping[int, int]) -> float:
    """How many users engaged positively, log-scaled relative to the most popular experience.

    log1p squashes the long tail: 1 fan vs 0 matters more than 41 vs 40.
    """
    top = max(fans.values(), default=0)
    return math.log1p(fans.get(exp.id, 0)) / math.log1p(top) if top else 0.0


def freshness(exp: ExperienceInfo, now: datetime, config: RecommenderConfig) -> float:
    """1.0 for a brand-new experience, halving every freshness_half_life_days."""
    return recency_weight(exp.created_at, now, config.freshness_half_life_days)


def novelty(exp: ExperienceInfo, profile: UserProfile) -> float:
    """1 if the user has never interacted with this experience, else 0."""
    return 0.0 if exp.id in profile.seen else 1.0


def compute_features(
    exp: ExperienceInfo,
    profile: UserProfile,
    fans: Mapping[int, int],
    now: datetime,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> dict[str, float]:
    return {
        "category_match": category_match(exp, profile),
        "interaction_preference": interaction_preference(exp, profile, config),
        "difficulty_match": difficulty_match(exp, profile, config),
        "duration_match": duration_match(exp, profile),
        "cost_match": cost_match(exp, profile, config),
        "popularity": popularity(exp, fans),
        "freshness": freshness(exp, now, config),
        "novelty": novelty(exp, profile),
    }


def weighted_score(features: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """score = Σ wᵢ·fᵢ / Σ wᵢ, in [0, 1] because every fᵢ is in [0, 1]."""
    total = sum(weights.values())
    return sum(w * features[name] for name, w in weights.items()) / total if total else 0.0
