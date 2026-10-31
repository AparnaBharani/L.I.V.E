"""What the append-only log currently means for one user and one experience.

The log records everything that happened. This module interprets it, and is the one
place that defines the rules, so the profile, popularity and the API all agree:

  - Each event type counts once per experience, at its latest time. Repeating an
    action adds no signal, so one person cannot inflate their own preferences.
  - Reversals remove what they reverse. unsave/unlike are undos, not negative
    feedback: saving then unsaving leaves no save signal behind.
  - Later feedback replaces contradicting feedback: like clears dislike and vice
    versa, and any positive action clears an earlier skip.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from app.enums import EventType as E


@dataclass
class ExperienceState:
    active: dict[E, datetime] = field(default_factory=dict)  # event type -> latest time it applies

    def apply(self, event_type: E, at: datetime) -> None:
        if event_type is E.UNSAVE:
            self.active.pop(E.SAVE, None)
        elif event_type is E.UNLIKE:
            self.active.pop(E.LIKE, None)
        else:
            self.active[event_type] = at
        if event_type is E.LIKE:
            self.active.pop(E.DISLIKE, None)
        elif event_type is E.DISLIKE:
            self.active.pop(E.LIKE, None)
        if event_type in (E.SAVE, E.LIKE, E.COMPLETE):
            self.active.pop(E.SKIP, None)

    @property
    def saved(self) -> bool:
        return E.SAVE in self.active

    @property
    def liked(self) -> bool:
        return E.LIKE in self.active

    @property
    def disliked(self) -> bool:
        return E.DISLIKE in self.active

    @property
    def completed(self) -> bool:
        return E.COMPLETE in self.active

    @property
    def skipped(self) -> bool:
        return E.SKIP in self.active


def replay(events: Iterable[tuple[int, E, datetime]]) -> dict[int, ExperienceState]:
    """(experience_id, event_type, occurred_at) in time order -> state per experience."""
    states: dict[int, ExperienceState] = {}
    for experience_id, event_type, occurred_at in events:
        states.setdefault(experience_id, ExperienceState()).apply(event_type, occurred_at)
    return states
