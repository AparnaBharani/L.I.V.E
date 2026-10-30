"""Measure retrieval on hand-labelled queries (read-only, uses DATABASE_URL).

Run from backend/ after seeding and embedding:   python -m scripts.evaluate_search

Recall@5  share of the relevant experiences found in the top 5
MRR       1 / rank of the first relevant result, averaged: how soon a good answer appears
Answered  share of queries with at least one relevant result in the top 5

The labels were written by the developer, over a catalogue of 42 items, so these numbers
compare retrievers against each other. They do not estimate real-world search quality.
"""

import json
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Experience
from app.recommender.evaluation import recall_at_k
from app.search.embedding import get_embedder
from app.search.service import retrieve

LABELS = Path(__file__).resolve().parent.parent / "tests" / "data" / "search_relevance.json"
K = 5


def score(db, embedder, queries, titles, mode):
    recall = mrr = answered = 0.0
    for item in queries:
        relevant = {titles[t] for t in item["relevant"]}
        ranked = [h.experience_id for h in retrieve(db, embedder, item["q"], mode=mode).hits]
        recall += recall_at_k(ranked, relevant, K)
        answered += bool(relevant & set(ranked[:K]))
        mrr += next((1 / rank for rank, i in enumerate(ranked, start=1) if i in relevant), 0.0)
    n = len(queries)
    return recall / n, mrr / n, answered / n


def main() -> None:
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    embedder = get_embedder()
    if embedder is None:
        raise SystemExit("The embedding model is unavailable.")
    with SessionLocal() as db:
        titles = dict(db.execute(select(Experience.title, Experience.id)).all())
        groups = {name: labels[name] for name in ("exact", "paraphrase", "constrained")}
        groups["all"] = [q for name in ("exact", "paraphrase", "constrained") for q in labels[name]]
        for name, queries in groups.items():
            print(f"\n{name} ({len(queries)} queries)")
            print(f"  {'retriever':10} {'Recall@5':>9} {'MRR':>6} {'Answered':>9}")
            for mode in ("keyword", "semantic", "hybrid"):
                recall, mrr, answered = score(db, embedder, queries, titles, mode)
                print(f"  {mode:10} {recall:9.3f} {mrr:6.3f} {answered:9.3f}")

        print("\noff-catalogue queries (fewer results is better)")
        for q in labels["off_catalogue"]:
            counts = {m: len(retrieve(db, embedder, q, mode=m).hits) for m in ("keyword", "semantic", "hybrid")}
            print(f"  {q:32} {counts}")


if __name__ == "__main__":
    main()
