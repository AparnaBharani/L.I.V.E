"""Every tunable number in the recommender lives here.

These are hand-chosen starting values, not learned or "true" ones. V6 replaces
hand-tuning with weights fitted against an evaluation metric.
"""

from dataclasses import dataclass, field

from app.enums import EventType as E


def _event_weights() -> dict[E, float]:
    # How much one event says about the user's interest in that experience.
    # Reversals cancel the original event exactly (save +4, unsave -4).
    return {
        E.VIEW: 1.0,
        E.CLICK: 2.0,
        E.SAVE: 4.0,
        E.UNSAVE: -4.0,
        E.LIKE: 5.0,
        E.UNLIKE: -5.0,
        E.COMPLETE: 6.0,
        E.SKIP: -3.0,
        E.DISLIKE: -5.0,
        E.SEARCH: 0.0,  # no experience attached; query text is used from V3 on
    }


def _feature_weights() -> dict[str, float]:
    # Relative importance of each feature in the personalized score (normalised by their sum).
    # Category carries the most weight: it is the clearest signal of taste. Popularity and
    # freshness are the same for every user, so they get little weight here (they drive
    # cold start instead). Chosen with `python -m scripts.evaluate` on seeded data; see README.
    return {
        "category_match": 0.40,
        "interaction_preference": 0.15,
        "difficulty_match": 0.10,
        "duration_match": 0.10,
        "cost_match": 0.10,
        "popularity": 0.05,
        "freshness": 0.05,
        "novelty": 0.05,
    }


def _cold_start_weights() -> dict[str, float]:
    # No behaviour yet, so only item-level signals: no preference feature is used.
    return {"popularity": 0.6, "freshness": 0.4}


@dataclass(frozen=True)
class RecommenderConfig:
    event_weights: dict[E, float] = field(default_factory=_event_weights)
    feature_weights: dict[str, float] = field(default_factory=_feature_weights)
    cold_start_weights: dict[str, float] = field(default_factory=_cold_start_weights)

    # Recency: an event loses half its weight every this many days (exponential decay).
    recency_half_life_days: float = 30.0
    # Freshness: an experience's "newness" halves every this many days after creation.
    freshness_half_life_days: float = 60.0

    # Events that count a user as a "fan" of an experience for popularity.
    popularity_events: frozenset[E] = frozenset({E.SAVE, E.LIKE, E.COMPLETE})

    # Category affinity = category sum / max(strongest category sum, this). A category needs
    # about this much recency-weighted evidence (≈ view+click+save+like) to count fully, so
    # a single view is a nudge, not certainty.
    category_evidence_scale: float = 10.0

    # Ordinal scale for difficulty. Unknown difficulty values score as neutral.
    difficulty_levels: dict[str, int] = field(
        default_factory=lambda: {"beginner": 0, "intermediate": 1, "advanced": 2}
    )
    # Cost match = (preferred + s) / (cost + s) when pricier than usual; s stops tiny
    # budgets (e.g. free) from making every paid item score ~0.
    cost_smoothing: float = 100.0
    # Item affinity (sum of weighted events) → [0, 1] via tanh(affinity / scale).
    interaction_scale: float = 5.0

    # Diversity: each earlier pick from the same category multiplies a candidate's score by this.
    # 1.0 disables it; lower = more variety but less accuracy (see the trade-off table in README).
    diversity_decay: float = 0.9

    exclude_completed: bool = True
    exclude_disliked: bool = True

    max_reasons: int = 3


DEFAULT_CONFIG = RecommenderConfig()

# Feature value meaning "we have no information": preference features default to it.
NEUTRAL = 0.5
