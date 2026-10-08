"""Stage 4: ordering (B6) and diversity re-ranking (B9)."""

from collections import Counter
from dataclasses import dataclass

from .models import ExperienceInfo


@dataclass(frozen=True)
class Scored:
    experience: ExperienceInfo
    relevance: float
    features: dict[str, float]


@dataclass(frozen=True)
class Ranked:
    experience: ExperienceInfo
    relevance: float
    score: float  # relevance after the diversity adjustment
    features: dict[str, float]


def rank(scored: list[Scored]) -> list[Scored]:
    """Highest relevance first; ties broken by experience id so the order is deterministic."""
    return sorted(scored, key=lambda s: (-s.relevance, s.experience.id))


def diversify(ranked: list[Scored], decay: float) -> list[Ranked]:
    """Greedy re-rank that discourages long runs of one category.

    At each position, pick the candidate maximising
        relevance × decay ** (how many already-picked items share its category).
    With decay = 0.9, a second item from a category needs to be ~11% more relevant
    than the best item from an unused category to win the slot, a third ~23% more.
    Strong preferences can still fill several slots; weak ones cannot. decay = 1 disables it.
    """
    remaining = list(ranked)  # already in deterministic relevance order
    picked: list[Ranked] = []
    per_category: Counter[str] = Counter()
    while remaining:
        # max() keeps the first of equal values, so ties go to the earlier (more relevant / lower id) item
        best = max(
            range(len(remaining)),
            key=lambda i: remaining[i].relevance * decay ** per_category[remaining[i].experience.category],
        )
        s = remaining.pop(best)
        score = s.relevance * decay ** per_category[s.experience.category]
        per_category[s.experience.category] += 1
        picked.append(Ranked(s.experience, s.relevance, score, s.features))
    return picked
