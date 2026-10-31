"""Orchestration (B11).

recommend()          the pure pipeline: profile → candidates → features → score → rank → diversify → explain
recommend_for_user() loads the inputs from PostgreSQL and calls recommend()
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EventType
from app.models import Experience, Interaction
from app.search.embedding import MODEL_NAME

from .candidates import generate_candidates
from .config import DEFAULT_CONFIG, RecommenderConfig
from .explain import explain
from .models import Event, ExperienceInfo, Recommendation, RecommendationResult
from .profile import build_profile
from .ranking import Scored, diversify, rank
from .scoring import closest_engaged, compute_features, taste_vector, weighted_score
from .state import ExperienceState, replay


def count_fans(
    rows: Iterable[tuple[int, int, EventType, datetime]],
    config: RecommenderConfig = DEFAULT_CONFIG,
) -> dict[int, int]:
    """(user_id, experience_id, event_type, occurred_at) in time order → current fans per experience."""
    states = replay(((user_id, experience_id), event_type, at) for user_id, experience_id, event_type, at in rows)
    return dict(Counter(
        experience_id for (_, experience_id), state in states.items()
        if state.active.keys() & config.popularity_events
    ))


def recommend(
    experiences: Sequence[ExperienceInfo],
    user_events: Sequence[Event],
    fans: Mapping[int, int],
    now: datetime,
    *,
    limit: int = 10,
    offset: int = 0,
    config: RecommenderConfig = DEFAULT_CONFIG,
    embeddings: Mapping[int, Sequence[float]] | None = None,
    retrieved: Mapping[int, float] | None = None,
) -> RecommendationResult:
    """retrieved, from search, limits candidates to those ids and scores them by relevance.

    Retrieval decides what may appear; this function decides the order for this user.
    """
    embeddings = embeddings or {}
    by_id = {e.id: e for e in experiences}
    profile = build_profile(user_events, by_id, now, config)

    # Cold start: with no behaviour there is nothing to personalise on, so rank by
    # item-level signals only (popularity + freshness) and say so in the response.
    strategy = "cold_start" if profile.is_cold_start else "personalized"
    weights = config.cold_start_weights if strategy == "cold_start" else config.feature_weights

    weights = {name: w for name, w in weights.items() if w > 0}  # a feature at 0 is switched off

    pool = experiences if retrieved is None else [e for e in experiences if e.id in retrieved]
    candidates, excluded = generate_candidates(pool, profile, config)
    taste = taste_vector(profile, embeddings)

    if retrieved is not None:
        share = config.query_match_share
        weights = {**weights, "query_match": sum(weights.values()) * share / (1 - share)}
    best_match = max(retrieved.values(), default=0.0) if retrieved else 0.0

    scored = []
    for exp in candidates:
        features = compute_features(exp, profile, fans, now, config, taste, embeddings)
        if retrieved is not None:
            features["query_match"] = retrieved[exp.id] / best_match if best_match else 0.0
        features = {name: features[name] for name in weights}  # report only what is used
        scored.append(Scored(exp, weighted_score(features, weights), features))

    # Someone searching asked for something specific, so the list is not spread across categories.
    decay = 1.0 if retrieved is not None else config.diversity_decay
    ordered = diversify(rank(scored), decay)
    engaged = sorted(profile.saved | profile.liked | profile.completed)
    page = ordered[offset : offset + limit]
    items = []
    for i, r in enumerate(page):
        closest = closest_engaged(r.experience, engaged, embeddings)
        similar = (by_id[closest[0]], closest[1]) if closest else None
        items.append(Recommendation(
            experience=r.experience,
            rank=offset + i + 1,
            score=round(r.score, 4),
            relevance=round(r.relevance, 4),
            features={k: round(v, 4) for k, v in r.features.items()},
            reasons=explain(r.experience, r.features, profile, strategy, config, similar),
            similar_to=closest[0] if closest else None,
        ))
    return RecommendationResult(strategy, items, len(candidates), excluded)


# ---------- database loading ----------

def to_info(exp: Experience) -> ExperienceInfo:
    return ExperienceInfo(
        id=exp.id, title=exp.title, category=exp.category, difficulty=exp.difficulty,
        duration_minutes=exp.duration_minutes, cost=exp.cost, created_at=exp.created_at,
    )


def load_fans(db: Session, config: RecommenderConfig = DEFAULT_CONFIG) -> dict[int, int]:
    rows = db.execute(
        select(Interaction.user_id, Interaction.experience_id, Interaction.event_type, Interaction.occurred_at)
        .where(Interaction.experience_id.is_not(None))
        .order_by(Interaction.occurred_at, Interaction.id)
    ).all()
    return count_fans(((r.user_id, r.experience_id, EventType(r.event_type), r.occurred_at) for r in rows), config)


def load_embeddings(db: Session) -> dict[int, list[float]]:
    """Stored vectors from the current model. Empty if nothing has been embedded yet."""
    rows = db.execute(
        select(Experience.id, Experience.embedding)
        .where(Experience.embedding.is_not(None), Experience.embedding_model == MODEL_NAME)
    ).all()
    return {r.id: r.embedding for r in rows}


def load_user_events(db: Session, user_id: int) -> list[Event]:
    rows = db.execute(
        select(Interaction.experience_id, Interaction.event_type, Interaction.occurred_at)
        .where(Interaction.user_id == user_id)
        .order_by(Interaction.occurred_at, Interaction.id)
    ).all()
    return [Event(r.experience_id, EventType(r.event_type), r.occurred_at) for r in rows]


def load_experience_states(db: Session, user_id: int) -> dict[int, ExperienceState]:
    """The user's current state per experience, from their whole history."""
    return replay(
        (e.experience_id, e.event_type, e.occurred_at)
        for e in load_user_events(db, user_id) if e.experience_id is not None
    )


def recommend_for_user(
    db: Session,
    user_id: int,
    *,
    now: datetime,
    limit: int = 10,
    offset: int = 0,
    config: RecommenderConfig = DEFAULT_CONFIG,
    retrieved: Mapping[int, float] | None = None,
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
        embeddings=load_embeddings(db),
        retrieved=retrieved,
    )
    return result, {e.id: e for e in orm_experiences}
