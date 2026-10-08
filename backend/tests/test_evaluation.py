"""Evaluation regression test: on the seeded demo data (in the TEST database), V2 must
beat the random and popularity baselines. Guards against changes that silently make
recommendations worse. Synthetic data, so this is a sanity floor, not proof of quality.
"""

from datetime import datetime, timezone

import pytest

from app.recommender.evaluation import evaluate, popularity_ranker, random_ranker, v2_ranker
from scripts.evaluate import load
from scripts.seed import seed

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def seeded(db_session):
    seed(db_session, NOW)
    return load(db_session)


@pytest.mark.parametrize("k", [5, 10])
def test_v2_beats_baselines(seeded, k):
    experiences, events = seeded
    v2 = evaluate(experiences, events, v2_ranker(), k=k)
    pop = evaluate(experiences, events, popularity_ranker, k=k)
    rand = [evaluate(experiences, events, random_ranker(s), k=k) for s in range(10)]
    rand_recall = sum(r["recall"] for r in rand) / len(rand)

    assert v2["users"] >= 10
    assert v2["recall"] > 2 * rand_recall
    assert v2["recall"] > 2 * pop["recall"]
    assert v2["ndcg"] > pop["ndcg"]


def test_diversity_keeps_several_categories_in_top5(seeded):
    experiences, events = seeded
    assert evaluate(experiences, events, v2_ranker(), k=5)["categories"] >= 3
