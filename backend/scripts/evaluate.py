"""Offline evaluation of the V2 recommender on the interactions in DATABASE_URL (read-only).

Run from backend/:   python -m scripts.evaluate
See app/recommender/evaluation.py for the protocol and metric definitions.
"""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.config import settings
from app.database import SessionLocal
from app.enums import EventType
from app.models import Experience, Interaction
from app.recommender.config import DEFAULT_CONFIG
from app.recommender.evaluation import (
    UserEvent,
    evaluate,
    popularity_ranker,
    random_ranker,
    temporal_holdout,
    v2_ranker,
)
from app.recommender.models import Event
from app.recommender.service import load_embeddings, to_info

RANDOM_SEEDS = 20


def load(db):
    experiences = [to_info(e) for e in db.scalars(select(Experience).order_by(Experience.id))]
    rows = db.execute(select(Interaction.user_id, Interaction.experience_id,
                             Interaction.event_type, Interaction.occurred_at)).all()
    events = [UserEvent(r.user_id, Event(r.experience_id, EventType(r.event_type), r.occurred_at)) for r in rows]
    return experiences, events


def with_semantic_weight(weight: float):
    return replace(DEFAULT_CONFIG, feature_weights={**DEFAULT_CONFIG.feature_weights, "semantic_match": weight})


def average(results: list[dict]) -> dict:
    return {key: sum(r[key] for r in results) / len(results) for key in results[0]}


def main() -> None:
    print(f"Evaluating on database '{make_url(settings.DATABASE_URL).database}' (read-only)")
    with SessionLocal() as db:
        experiences, events = load(db)
        embeddings = load_embeddings(db)
    cases = temporal_holdout(events)
    print(f"{len(experiences)} experiences, {len(events)} events, {len(cases)} users with enough history "
          f"(2 held-out positives each)\n")

    rankers = {
        "random (avg of 20 seeds)": None,
        "popularity": popularity_ranker,
        "rules only (V2 baseline)": v2_ranker(with_semantic_weight(0.0)),
        "current": v2_ranker(DEFAULT_CONFIG, embeddings),
        "current, no diversity": v2_ranker(replace(DEFAULT_CONFIG, diversity_decay=1.0), embeddings),
        "semantic_match 0.30": v2_ranker(with_semantic_weight(0.30), embeddings),
    }
    for k in (5, 10):
        print(f"K = {k}")
        print(f"  {'ranker':26} {'Precision':>9} {'Recall':>7} {'NDCG':>6} {'Coverage':>9} {'Categories':>10}")
        for name, ranker in rankers.items():
            if ranker is None:
                m = average([evaluate(experiences, events, random_ranker(s), k=k) for s in range(RANDOM_SEEDS)])
            else:
                m = evaluate(experiences, events, ranker, k=k)
            print(f"  {name:26} {m['precision']:9.3f} {m['recall']:7.3f} {m['ndcg']:6.3f} "
                  f"{m['coverage']:9.3f} {m['categories']:10.2f}")
        print()


if __name__ == "__main__":
    main()
