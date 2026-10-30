"""Candidate retrieval. Each retriever returns experience ids, best first."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy import String, cast, func, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models import Experience

from .embedding import Embedder

RRF_K = 60  # the standard constant: damps the gap between the very top ranks
# Below this cosine similarity a passage is treated as unrelated, not merely far down the list.
# Specific to the model. Set by scripts/evaluate_search.py: the weakest labelled match scored
# 0.567 and the best match for an off-catalogue query scored 0.543.
MIN_SIMILARITY = 0.56


@dataclass(frozen=True)
class Filters:
    """Hard constraints: an experience outside them is never returned."""

    category: str | None = None
    difficulty: str | None = None
    max_cost: int | None = None
    max_duration_minutes: int | None = None


def apply_filters(stmt: Select, filters: Filters) -> Select:
    if filters.category is not None:
        stmt = stmt.where(Experience.category == filters.category)
    if filters.difficulty is not None:
        stmt = stmt.where(Experience.difficulty == filters.difficulty)
    if filters.max_cost is not None:
        stmt = stmt.where(Experience.cost <= filters.max_cost)
    if filters.max_duration_minutes is not None:
        stmt = stmt.where(Experience.duration_minutes <= filters.max_duration_minutes)
    return stmt


def keyword_search(db: Session, text: str, filters: Filters, limit: int) -> list[int]:
    """PostgreSQL full-text search: stemmed words, ranked with title above description.

    plainto_tsquery ANDs every word, so a long natural sentence would match nothing.
    Swapping & for | means "any of these words", and ts_rank rewards matching more of them.
    """
    query = cast(func.replace(cast(func.plainto_tsquery("english", text), String), "&", "|"), TSQUERY)
    stmt = (
        select(Experience.id)
        .where(Experience.search_vector.op("@@")(query))
        .order_by(func.ts_rank(Experience.search_vector, query).desc(), Experience.id)
        .limit(limit)
    )
    return list(db.scalars(apply_filters(stmt, filters)))


def semantic_search(db: Session, embedder: Embedder, text: str, filters: Filters, limit: int) -> list[int]:
    """Cosine similarity between the query and every stored vector.

    A full scan in Python is fine for a small catalogue. The measured reason to move to
    pgvector and an approximate index would be this scan becoming slow, not fashion.
    """
    stmt = select(Experience.id, Experience.embedding).where(
        Experience.embedding.is_not(None), Experience.embedding_model == embedder.name
    )
    rows = db.execute(apply_filters(stmt, filters)).all()
    if not rows:
        return []
    ids = [r.id for r in rows]
    matrix = np.array([r.embedding for r in rows], dtype=np.float32)
    query = np.array(embedder.embed_query(text), dtype=np.float32)
    similarity = (matrix @ query) / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(query))
    ranked = sorted(zip(similarity.tolist(), ids), key=lambda pair: (-pair[0], pair[1]))
    return [i for score, i in ranked if score >= MIN_SIMILARITY][:limit]


@dataclass(frozen=True)
class Fused:
    experience_id: int
    score: float
    ranks: dict[str, int]  # retriever name -> 1-based rank


def reciprocal_rank_fusion(rankings: dict[str, Sequence[int]], k: int = RRF_K) -> list[Fused]:
    """Merge rankings using positions only: score = sum of 1 / (k + rank).

    Keyword and cosine scores are on unrelated scales, so they cannot be added directly.
    Ties are broken by id, so the result is deterministic.
    """
    ranks: dict[int, dict[str, int]] = {}
    for source, ids in rankings.items():
        for position, experience_id in enumerate(ids, start=1):
            ranks.setdefault(experience_id, {})[source] = position
    fused = [Fused(i, sum(1 / (k + r) for r in found.values()), found) for i, found in ranks.items()]
    return sorted(fused, key=lambda f: (-f.score, f.experience_id))
