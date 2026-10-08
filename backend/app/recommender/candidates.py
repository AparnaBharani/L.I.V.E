"""Stage 2: candidate generation (B5): which experiences are eligible at all.

Kept separate from ranking so that later versions can add other candidate sources
(keyword search in V4, vector search in V4, graph neighbours in V7) without
touching the scoring code.
"""

from collections.abc import Iterable

from .config import DEFAULT_CONFIG, RecommenderConfig
from .models import ExperienceInfo, UserProfile


def generate_candidates(
    experiences: Iterable[ExperienceInfo],
    profile: UserProfile,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> tuple[list[ExperienceInfo], dict[int, str]]:
    """Return (candidates, excluded) where excluded maps experience id → reason."""
    candidates: list[ExperienceInfo] = []
    excluded: dict[int, str] = {}
    for exp in experiences:
        if config.exclude_completed and exp.id in profile.completed:
            excluded[exp.id] = "already completed"
        elif config.exclude_disliked and exp.id in profile.disliked:
            excluded[exp.id] = "disliked"
        else:
            candidates.append(exp)
    return candidates, excluded
