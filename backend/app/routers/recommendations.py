from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import DbSession, ExistingUser, Offset
from app.recommender.service import recommend_for_user
from app.schemas import ExperienceResponse, RecommendationItem, RecommendationsResponse
from app.search.embedding import Embedder, get_embedder
from app.search.service import retrieve

router = APIRouter(prefix="/users/{user_id}/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationsResponse)
def get_recommendations(
    user: ExistingUser,
    db: DbSession,
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Offset = 0,
    q: Annotated[str | None, Query(max_length=300, description="Rank these search results for the user.")] = None,
):
    # The route only translates HTTP <-> the recommender; the algorithm lives in app/recommender/.
    now = datetime.now(timezone.utc)
    retrieved = None
    if q is not None:
        hits = retrieve(db, embedder, q.replace("\x00", " ")).hits
        # Items that only satisfy filters have no relevance score, so all count equally.
        retrieved = {h.experience_id: h.score or 1.0 for h in hits}
    result, experiences = recommend_for_user(db, user.id, now=now, limit=limit, offset=offset, retrieved=retrieved)
    return RecommendationsResponse(
        user_id=user.id,
        strategy=result.strategy,
        generated_at=now,
        candidate_count=result.candidate_count,
        items=[
            RecommendationItem(
                rank=r.rank,
                score=r.score,
                relevance=r.relevance,
                reasons=r.reasons,
                features=r.features,
                experience=ExperienceResponse.model_validate(experiences[r.experience.id]),
            )
            for r in result.items
        ],
    )
