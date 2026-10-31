from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.dependencies import DbSession, Limit, Offset
from app.models import Experience
from app.schemas import MAX_INT, ExperienceResponse, ParsedQueryResponse, SearchHitResponse, SearchResponse
from app.search.embedding import Embedder, get_embedder
from app.search.retrieval import Filters
from app.search.service import retrieve

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    db: DbSession,
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
    q: Annotated[str, Query(max_length=300)] = "",
    category: Annotated[str | None, Query(max_length=50)] = None,
    difficulty: Annotated[str | None, Query(max_length=50)] = None,
    max_cost: Annotated[int | None, Query(ge=0, le=MAX_INT)] = None,
    max_duration_minutes: Annotated[int | None, Query(gt=0, le=MAX_INT)] = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    result = retrieve(db, embedder, q.replace("\x00", " "), Filters(category, difficulty, max_cost, max_duration_minutes))
    page = result.hits[offset : offset + limit]
    experiences = {e.id: e for e in db.scalars(
        select(Experience).where(Experience.id.in_([h.experience_id for h in page]))
    )}
    return SearchResponse(
        query=q,
        mode=result.mode,
        understood=ParsedQueryResponse(
            text=result.parsed.text,
            categories=list(result.parsed.categories),
            category=result.filters.category,
            difficulty=result.filters.difficulty,
            max_cost=result.filters.max_cost,
            max_duration_minutes=result.filters.max_duration_minutes,
        ),
        total=len(result.hits),
        items=[
            SearchHitResponse(
                score=round(h.score, 5),
                keyword_rank=h.keyword_rank,
                semantic_rank=h.semantic_rank,
                category_hint=h.category_hint,
                experience=ExperienceResponse.model_validate(experiences[h.experience_id]),
            )
            for h in page
        ],
    )
