from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ExistingUser, Limit, Offset, get_or_404
from app.models import Experience, Interaction
from app.recommender.service import load_experience_states
from app.schemas import ExperienceStateResponse, InteractionCreate, InteractionResponse

# Events are nested under the user who performed them.
router = APIRouter(prefix="/users/{user_id}/interactions", tags=["interactions"])


@router.post("", response_model=InteractionResponse, status_code=status.HTTP_201_CREATED)
def create_interaction(payload: InteractionCreate, user: ExistingUser, db: DbSession):
    # By now InteractionCreate has already enforced the event shape, so
    # experience_id is set exactly when the event is about an experience.
    if payload.experience_id is not None:
        get_or_404(db, Experience, payload.experience_id)

    # user_id comes from the URL, never from the request body.
    user_id = user.id
    interaction = Interaction(user_id=user_id, **payload.model_dump())
    db.add(interaction)
    try:
        db.commit()
    except IntegrityError as exc:
        # The user or experience was deleted between the checks above and this INSERT.
        db.rollback()
        constraint = getattr(exc.orig.diag, "constraint_name", None)
        if constraint == "fk_interactions_experience_id_experiences":
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Experience {payload.experience_id} not found")
        if constraint == "fk_interactions_user_id_users":
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
        raise
    db.refresh(interaction)  # load server-set values (id, occurred_at)
    return interaction


@router.get("/state", response_model=list[ExperienceStateResponse])
def get_interaction_state(user: ExistingUser, db: DbSession):
    """What is currently saved, liked, disliked, completed or skipped, from the whole history."""
    return [
        ExperienceStateResponse(experience_id=experience_id, saved=s.saved, liked=s.liked,
                                disliked=s.disliked, completed=s.completed, skipped=s.skipped)
        for experience_id, s in sorted(load_experience_states(db, user.id).items())
        if s.saved or s.liked or s.disliked or s.completed or s.skipped
    ]


@router.get("", response_model=list[InteractionResponse])
def list_interactions(user: ExistingUser, db: DbSession, limit: Limit = 50, offset: Offset = 0):
    stmt = (
        select(Interaction)
        .where(Interaction.user_id == user.id)
        # Newest first; id breaks ties between events with the same timestamp.
        .order_by(Interaction.occurred_at.desc(), Interaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all()
