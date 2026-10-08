"""Offline evaluation (B13): replay history, hide each user's latest positives, and check
whether the recommender would have surfaced them.

Protocol (temporal leave-last-out):
  1. "Positive" experience = one the user saved, liked or completed (config.popularity_events).
  2. Order a user's positive experiences by their first positive event. Hold out the last
     `n_holdout`. The cutoff is the earliest event of any kind on a held-out experience.
  3. Training data = only events before the cutoff, for this user AND for popularity
     (other users' events after the cutoff would leak the future).
  4. Recommend as of the cutoff, then score the top-K against the held-out set.

Metrics (averaged over evaluated users):
  Precision@K  share of the K recommendations that were held-out positives
  Recall@K     share of the held-out positives that appear in the top K
  NDCG@K       like recall, but hits near the top count more (1/log2(rank+1)), scaled to [0, 1]
  Coverage@K   share of the catalogue that appears in anyone's top K
  Categories@K average number of distinct categories in a top-K list (diversity)
"""

import math
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from .candidates import generate_candidates
from .config import DEFAULT_CONFIG, RecommenderConfig
from .models import Event, ExperienceInfo
from .profile import build_profile
from .service import count_fans, recommend


@dataclass(frozen=True)
class UserEvent:
    user_id: int
    event: Event


@dataclass(frozen=True)
class HoldOutCase:
    user_id: int
    cutoff: datetime
    train_events: list[Event]
    held_out: frozenset[int]


# ---------- metrics (binary relevance) ----------

def precision_at_k(recommended: Sequence[int], relevant: set[int] | frozenset[int], k: int) -> float:
    return sum(1 for i in recommended[:k] if i in relevant) / k


def recall_at_k(recommended: Sequence[int], relevant: set[int] | frozenset[int], k: int) -> float:
    return sum(1 for i in recommended[:k] if i in relevant) / len(relevant) if relevant else 0.0


def ndcg_at_k(recommended: Sequence[int], relevant: set[int] | frozenset[int], k: int) -> float:
    dcg = sum(1 / math.log2(rank + 2) for rank, i in enumerate(recommended[:k]) if i in relevant)
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


# ---------- data split ----------

def temporal_holdout(
    events: Iterable[UserEvent],
    n_holdout: int = 2,
    min_train_positives: int = 2,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> list[HoldOutCase]:
    by_user: dict[int, list[Event]] = {}
    for ue in events:
        by_user.setdefault(ue.user_id, []).append(ue.event)

    cases = []
    for user_id, user_events in sorted(by_user.items()):
        user_events = sorted(user_events, key=lambda e: e.occurred_at)
        first_positive: dict[int, datetime] = {}
        for e in user_events:
            if e.experience_id is not None and e.event_type in config.popularity_events:
                first_positive.setdefault(e.experience_id, e.occurred_at)
        ordered = sorted(first_positive, key=lambda i: (first_positive[i], i))
        if len(ordered) < n_holdout + min_train_positives:
            continue  # not enough history to both learn from and test on
        held_out = frozenset(ordered[-n_holdout:])
        cutoff = min(e.occurred_at for e in user_events if e.experience_id in held_out)
        train = [e for e in user_events if e.occurred_at < cutoff]
        cases.append(HoldOutCase(user_id, cutoff, train, held_out))
    return cases


# ---------- rankers under test ----------

Ranker = Callable[[Sequence[ExperienceInfo], HoldOutCase, dict[int, int], int], list[int]]


def v2_ranker(config: RecommenderConfig = DEFAULT_CONFIG) -> Ranker:
    def rank(experiences, case, fans, k):
        result = recommend(experiences, case.train_events, fans, case.cutoff, limit=k, config=config)
        return [r.experience.id for r in result.items]
    return rank


def popularity_ranker(experiences, case, fans, k):
    """Baseline: most fans first, same candidate exclusions as V2, no personalisation."""
    profile = build_profile(case.train_events, {e.id: e for e in experiences}, case.cutoff)
    candidates, _ = generate_candidates(experiences, profile)
    return [e.id for e in sorted(candidates, key=lambda e: (-fans.get(e.id, 0), e.id))[:k]]


def random_ranker(seed: int = 0) -> Ranker:
    """Baseline: a random order of the same candidates (reproducible per user)."""
    def rank(experiences, case, fans, k):
        profile = build_profile(case.train_events, {e.id: e for e in experiences}, case.cutoff)
        candidates, _ = generate_candidates(experiences, profile)
        ids = [e.id for e in candidates]
        random.Random(seed * 100_003 + case.user_id).shuffle(ids)
        return ids[:k]
    return rank


# ---------- evaluation ----------

def evaluate(
    experiences: Sequence[ExperienceInfo],
    events: Sequence[UserEvent],
    ranker: Ranker,
    k: int = 5,
    n_holdout: int = 2,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> dict[str, float]:
    cases = temporal_holdout(events, n_holdout=n_holdout, config=config)
    category_of = {e.id: e.category for e in experiences}
    totals = {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "categories": 0.0}
    shown: set[int] = set()
    for case in cases:
        # Popularity as it was at the cutoff: no one's future events.
        fans = count_fans(
            (ue.user_id, ue.event.experience_id) for ue in events
            if ue.event.occurred_at < case.cutoff
            and ue.event.event_type in config.popularity_events
            and ue.event.experience_id is not None
        )
        recommended = ranker(experiences, case, fans, k)
        totals["precision"] += precision_at_k(recommended, case.held_out, k)
        totals["recall"] += recall_at_k(recommended, case.held_out, k)
        totals["ndcg"] += ndcg_at_k(recommended, case.held_out, k)
        totals["categories"] += len({category_of[i] for i in recommended})
        shown.update(recommended)
    n = len(cases)
    metrics = {name: (value / n if n else 0.0) for name, value in totals.items()}
    metrics["coverage"] = len(shown) / len(experiences) if experiences else 0.0
    metrics["users"] = n
    return metrics
