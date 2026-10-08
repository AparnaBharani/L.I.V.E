"""Stage 1: turn a user's event log into a preference profile (B3 + B4)."""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime

from app.enums import EventType as E

from .config import DEFAULT_CONFIG, RecommenderConfig
from .models import Event, ExperienceInfo, UserProfile


def recency_weight(occurred_at: datetime, now: datetime, half_life_days: float) -> float:
    """Exponential decay: 1.0 now, 0.5 after one half-life, 0.25 after two, ...

    weight = 0.5 ** (age_in_days / half_life_days). Future timestamps count as "now".
    """
    age_days = max(0.0, (now - occurred_at).total_seconds() / 86_400)
    return 0.5 ** (age_days / half_life_days)


def _replay_state(profile: UserProfile, experience_id: int, event_type: E) -> None:
    """Keep current saved/liked/disliked/completed state; the latest event wins."""
    if event_type is E.SAVE:
        profile.saved.add(experience_id)
    elif event_type is E.UNSAVE:
        profile.saved.discard(experience_id)
    elif event_type is E.LIKE:
        profile.liked.add(experience_id)
        profile.disliked.discard(experience_id)
    elif event_type is E.UNLIKE:
        profile.liked.discard(experience_id)
    elif event_type is E.DISLIKE:
        profile.disliked.add(experience_id)
        profile.liked.discard(experience_id)
    elif event_type is E.COMPLETE:
        profile.completed.add(experience_id)


def build_profile(
    events: Iterable[Event],
    experiences: Mapping[int, ExperienceInfo],
    now: datetime,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> UserProfile:
    profile = UserProfile()
    category_raw: dict[str, float] = defaultdict(float)
    item_raw: dict[int, float] = defaultdict(float)

    for event in sorted(events, key=lambda e: e.occurred_at):
        exp = experiences.get(event.experience_id) if event.experience_id is not None else None
        if exp is None:
            continue  # search events (no experience) or experiences no longer in the catalogue
        # signal = how much this event says × how recent it is
        signal = config.event_weights[event.event_type] * recency_weight(
            event.occurred_at, now, config.recency_half_life_days
        )
        category_raw[exp.category] += signal
        item_raw[exp.id] += signal
        profile.seen.add(exp.id)
        profile.signal_count += 1
        _replay_state(profile, exp.id, event.event_type)

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
