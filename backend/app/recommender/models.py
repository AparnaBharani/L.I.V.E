"""Plain data passed between pipeline stages (deliberately not ORM objects)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.enums import EventType

Strategy = Literal["personalized", "cold_start"]


@dataclass(frozen=True)
class ExperienceInfo:
    """The experience attributes the recommender uses."""

    id: int
    title: str
    category: str
    difficulty: str
    duration_minutes: int
    cost: int
    created_at: datetime


@dataclass(frozen=True)
class Event:
    """One of the user's interactions."""

    experience_id: int | None
    event_type: EventType
    occurred_at: datetime


@dataclass
class UserProfile:
    """What the event history says about one user."""

    # Recency-weighted event sums per category / max(strongest, evidence scale). Range [-1, 1].
    category_affinity: dict[str, float] = field(default_factory=dict)
    # Raw recency-weighted event sum per experience the user touched.
    item_affinity: dict[int, float] = field(default_factory=dict)
    # Averages over experiences with positive affinity, weighted by that affinity. None = unknown.
    preferred_difficulty: float | None = None   # on the difficulty_levels scale
    preferred_duration: float | None = None     # minutes (geometric mean)
    preferred_cost: float | None = None         # rupees
    # Current state, replayed from the log (latest event wins).
    seen: set[int] = field(default_factory=set)
    saved: set[int] = field(default_factory=set)
    liked: set[int] = field(default_factory=set)
    disliked: set[int] = field(default_factory=set)
    completed: set[int] = field(default_factory=set)
    signal_count: int = 0  # events attached to an experience

    @property
    def is_cold_start(self) -> bool:
        return self.signal_count == 0


@dataclass(frozen=True)
class Recommendation:
    experience: ExperienceInfo
    rank: int
    score: float                 # final score after the diversity adjustment (sets the order)
    relevance: float             # weighted feature score before diversity
    features: dict[str, float]
    reasons: list[str]


@dataclass(frozen=True)
class RecommendationResult:
    strategy: Strategy
    items: list[Recommendation]
    candidate_count: int
    excluded: dict[int, str]     # experience id → why it was not a candidate
