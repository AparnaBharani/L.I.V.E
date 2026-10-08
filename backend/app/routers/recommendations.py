from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import DbSession, ExistingUser, Offset
from app.recommender.service import recommend_for_user
from app.schemas import ExperienceResponse, RecommendationItem, RecommendationsResponse

router = APIRouter(prefix="/users/{user_id}/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationsResponse)
def get_recommendations(
    user: ExistingUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Offset = 0,
):
    # The route only translates HTTP <-> the recommender; the algorithm lives in app/recommender/.
    now = datetime.now(timezone.utc)
    result, experiences = recommend_for_user(db, user.id, now=now, limit=limit, offset=offset)
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
