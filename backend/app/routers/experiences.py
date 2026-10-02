from fastapi import APIRouter, status
from sqlalchemy import select

from app.dependencies import DbSession, Limit, Offset, get_or_404
from app.models import Experience
from app.schemas import ExperienceCreate, ExperienceResponse

router = APIRouter(prefix="/experiences", tags=["experiences"])


@router.post("", response_model=ExperienceResponse, status_code=status.HTTP_201_CREATED)
def create_experience(payload: ExperienceCreate, db: DbSession):
    experience = Experience(**payload.model_dump())
    db.add(experience)
    db.commit()
    db.refresh(experience)
    return experience


@router.get("", response_model=list[ExperienceResponse])
def list_experiences(db: DbSession, limit: Limit = 50, offset: Offset = 0):
    stmt = select(Experience).order_by(Experience.id).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@router.get("/{experience_id}", response_model=ExperienceResponse)
def get_experience(experience_id: int, db: DbSession):
    return get_or_404(db, Experience, experience_id)
