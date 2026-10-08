"""Orchestration (B11).

recommend()          the pure pipeline: profile → candidates → features → score → rank → diversify → explain
recommend_for_user() loads the inputs from PostgreSQL and calls recommend()
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EventType
from app.models import Experience, Interaction

from .candidates import generate_candidates
from .config import DEFAULT_CONFIG, RecommenderConfig
from .explain import explain
from .models import Event, ExperienceInfo, Recommendation, RecommendationResult
from .profile import build_profile
from .ranking import Scored, diversify, rank
from .scoring import compute_features, weighted_score


def count_fans(rows: Iterable[tuple[int, int]]) -> dict[int, int]:
    """(user_id, experience_id) rows of positive events → distinct users per experience."""
    users: dict[int, set[int]] = defaultdict(set)
    for user_id, experience_id in rows:
        users[experience_id].add(user_id)
    return {experience_id: len(u) for experience_id, u in users.items()}


def recommend(
    experiences: Sequence[ExperienceInfo],
    user_events: Sequence[Event],
    fans: Mapping[int, int],
    now: datetime,
    *,
    limit: int = 10,
    offset: int = 0,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> RecommendationResult:
    by_id = {e.id: e for e in experiences}
    profile = build_profile(user_events, by_id, now, config)

    # Cold start: with no behaviour there is nothing to personalise on, so rank by
    # item-level signals only (popularity + freshness) and say so in the response.
    strategy = "cold_start" if profile.is_cold_start else "personalized"
    weights = config.cold_start_weights if strategy == "cold_start" else config.feature_weights

    candidates, excluded = generate_candidates(experiences, profile, config)
    scored = []
    for exp in candidates:
        features = compute_features(exp, profile, fans, now, config)
        features = {name: features[name] for name in weights}  # report only what is used
        scored.append(Scored(exp, weighted_score(features, weights), features))

    ordered = diversify(rank(scored), config.diversity_decay)
    page = ordered[offset : offset + limit]
    items = [
        Recommendation(
            experience=r.experience,
            rank=offset + i + 1,
            score=round(r.score, 4),
            relevance=round(r.relevance, 4),
            features={k: round(v, 4) for k, v in r.features.items()},
            reasons=explain(r.experience, r.features, profile, strategy, config),
        )
        for i, r in enumerate(page)
    ]
    return RecommendationResult(strategy, items, len(candidates), excluded)


# ---------- database loading ----------

def to_info(exp: Experience) -> ExperienceInfo:
    return ExperienceInfo(
        id=exp.id, title=exp.title, category=exp.category, difficulty=exp.difficulty,
        duration_minutes=exp.duration_minutes, cost=exp.cost, created_at=exp.created_at,
    )


def load_fans(db: Session, config: RecommenderConfig = DEFAULT_CONFIG) -> dict[int, int]:
    # Simplification: a later unsave/unlike does not remove someone as a fan.
    rows = db.execute(
        select(Interaction.user_id, Interaction.experience_id)
        .where(Interaction.event_type.in_(config.popularity_events), Interaction.experience_id.is_not(None))
        .distinct()
    ).all()
    return count_fans((r.user_id, r.experience_id) for r in rows)


def load_user_events(db: Session, user_id: int) -> list[Event]:
    rows = db.execute(
        select(Interaction.experience_id, Interaction.event_type, Interaction.occurred_at)
        .where(Interaction.user_id == user_id)
    ).all()
    return [Event(r.experience_id, EventType(r.event_type), r.occurred_at) for r in rows]


def recommend_for_user(
    db: Session,
    user_id: int,
    *,
    now: datetime,
    limit: int = 10,
    offset: int = 0,
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> tuple[RecommendationResult, dict[int, Experience]]:
    """Returns the result plus the ORM experiences by id (for building the API response)."""
    orm_experiences = db.scalars(select(Experience).order_by(Experience.id)).all()
    result = recommend(
        [to_info(e) for e in orm_experiences],
        load_user_events(db, user_id),
        load_fans(db, config),
        now,
        limit=limit,
        offset=offset,
        config=config,
    )
    return result, {e.id: e for e in orm_experiences}
