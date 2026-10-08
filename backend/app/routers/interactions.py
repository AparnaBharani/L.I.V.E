from fastapi import APIRouter, status
from sqlalchemy import select

from app.dependencies import DbSession, ExistingUser, Limit, Offset, get_or_404
from app.models import Experience, Interaction
from app.schemas import InteractionCreate, InteractionResponse

# Events are nested under the user who performed them.
router = APIRouter(prefix="/users/{user_id}/interactions", tags=["interactions"])


@router.post("", response_model=InteractionResponse, status_code=status.HTTP_201_CREATED)
def create_interaction(payload: InteractionCreate, user: ExistingUser, db: DbSession):
    # By now InteractionCreate has already enforced the event shape, so
    # experience_id is set exactly when the event is about an experience.
    if payload.experience_id is not None:
        get_or_404(db, Experience, payload.experience_id)

    # user_id comes from the URL, never from the request body.
    interaction = Interaction(user_id=user.id, **payload.model_dump())
    db.add(interaction)
    db.commit()
    db.refresh(interaction)  # load server-set values (id, occurred_at)
    return interaction


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
