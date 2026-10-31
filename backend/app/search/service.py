"""Search orchestration: understand the query, retrieve, fuse. Knows nothing about the user."""

from dataclasses import dataclass, replace
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Experience

from .embedding import Embedder
from .query import ParsedQuery, parse_query
from .retrieval import RRF_K, Filters, apply_filters, keyword_search, reciprocal_rank_fusion, semantic_search

CANDIDATES_PER_RETRIEVER = 50
# A category hint is worth one top rank in one retriever: it can decide between close
# results, but it cannot outweigh an experience that matches in both retrievers.
CATEGORY_HINT_BONUS = 1 / (RRF_K + 1)

Mode = Literal["hybrid", "keyword", "browse"]


@dataclass(frozen=True)
class SearchHit:
    experience_id: int
    score: float
    keyword_rank: int | None
    semantic_rank: int | None
    category_hint: bool


@dataclass(frozen=True)
class SearchResult:
    parsed: ParsedQuery
    filters: Filters
    mode: Mode
    hits: list[SearchHit]


def retrieve(
    db: Session,
    embedder: Embedder | None,
    query: str,
    explicit: Filters = Filters(),
    mode: Literal["hybrid", "keyword", "semantic"] = "hybrid",
) -> SearchResult:
    """All matching hits, best first. Explicit filters win over ones read from the query."""
    parsed = parse_query(query)
    filters = replace(
        explicit,
        difficulty=explicit.difficulty if explicit.difficulty is not None else parsed.difficulty,
        max_cost=explicit.max_cost if explicit.max_cost is not None else parsed.max_cost,
        max_duration_minutes=(
            explicit.max_duration_minutes if explicit.max_duration_minutes is not None
            else parsed.max_duration_minutes
        ),
    )

    if not parsed.text:
        # Nothing to match on, only constraints: list everything that satisfies them.
        ids = db.scalars(apply_filters(select(Experience.id).order_by(Experience.id), filters))
        hits = [SearchHit(i, 0.0, None, None, False) for i in ids]
        return SearchResult(parsed, filters, "browse", hits)

    rankings: dict[str, list[int]] = {}
    if mode != "semantic":
        rankings["keyword"] = keyword_search(db, parsed.text, filters, CANDIDATES_PER_RETRIEVER)
    if mode != "keyword" and embedder is not None:
        rankings["semantic"] = semantic_search(db, embedder, parsed.text, filters, CANDIDATES_PER_RETRIEVER)

    fused = reciprocal_rank_fusion(rankings)
    hinted: set[int] = set()
    if parsed.categories and fused:
        hinted = set(db.scalars(select(Experience.id).where(
            Experience.id.in_([f.experience_id for f in fused]),
            Experience.category.in_(parsed.categories),
        )))

    hits = [
        SearchHit(
            experience_id=f.experience_id,
            score=f.score + (CATEGORY_HINT_BONUS if f.experience_id in hinted else 0.0),
            keyword_rank=f.ranks.get("keyword"),
            semantic_rank=f.ranks.get("semantic"),
            category_hint=f.experience_id in hinted,
        )
        for f in fused
    ]
    hits.sort(key=lambda h: (-h.score, h.experience_id))
    return SearchResult(parsed, filters, "hybrid" if "semantic" in rankings else "keyword", hits)
