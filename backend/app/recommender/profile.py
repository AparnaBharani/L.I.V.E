"""Stage 1: turn a user's event log into a preference profile (B3 + B4)."""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime

from .config import DEFAULT_CONFIG, RecommenderConfig
from .models import Event, ExperienceInfo, UserProfile
from .state import replay


def recency_weight(occurred_at: datetime, now: datetime, half_life_days: float) -> float:
    """Exponential decay: 1.0 now, 0.5 after one half-life, 0.25 after two, ...

    weight = 0.5 ** (age_in_days / half_life_days). Future timestamps count as "now".
    """
    age_days = max(0.0, (now - occurred_at).total_seconds() / 86_400)
    return 0.5 ** (age_days / half_life_days)


def build_profile(
    events: Iterable[Event],
    experiences: Mapping[int, ExperienceInfo],
    now: datetime,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> UserProfile:
    profile = UserProfile()
    category_raw: dict[str, float] = defaultdict(float)
    item_raw: dict[int, float] = defaultdict(float)

    # Skips search events (no experience) and experiences no longer in the catalogue.
    known = [e for e in sorted(events, key=lambda e: e.occurred_at) if e.experience_id in experiences]
    profile.signal_count = len(known)

    for experience_id, state in replay((e.experience_id, e.event_type, e.occurred_at) for e in known).items():
        exp = experiences[experience_id]
        # signal = how much each event type still in effect says × how recent it is
        signal = sum(
            config.event_weights[event_type] * recency_weight(at, now, config.recency_half_life_days)
            for event_type, at in state.active.items()
        )
        category_raw[exp.category] += signal
        item_raw[exp.id] += signal
        profile.seen.add(exp.id)
        for flag, members in ((state.saved, profile.saved), (state.liked, profile.liked),
                              (state.disliked, profile.disliked), (state.completed, profile.completed)):
            if flag:
                members.add(exp.id)

    # Category affinity in [-1, 1]. Dividing by the strongest category makes long and short
    # histories comparable; the evidence floor stops one weak event from looking like certainty.
    strongest = max((abs(v) for v in category_raw.values()), default=0.0)
    scale = max(strongest, config.category_evidence_scale)
    profile.category_affinity = {c: v / scale for c, v in category_raw.items()}
    profile.item_affinity = dict(item_raw)

    # Attribute preferences: what the experiences they responded well to have in common.
    # Each positively-engaged experience counts in proportion to how positive it was.
    liked_items = [(experiences[i], a) for i, a in item_raw.items() if a > 0]
    total = sum(a for _, a in liked_items)
    if total > 0:
        profile.preferred_cost = sum(e.cost * a for e, a in liked_items) / total
        # Geometric mean: durations are compared as ratios (60 vs 120 min = 30 vs 60 min).
        profile.preferred_duration = math.exp(
            sum(math.log(e.duration_minutes) * a for e, a in liked_items) / total
        )
        levelled = [(config.difficulty_levels[e.difficulty], a) for e, a in liked_items
                    if e.difficulty in config.difficulty_levels]
        level_total = sum(a for _, a in levelled)
        if level_total > 0:
            profile.preferred_difficulty = sum(lv * a for lv, a in levelled) / level_total

    return profile
