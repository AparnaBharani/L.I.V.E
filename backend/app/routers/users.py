from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ExistingUser, Limit, Offset
from app.models import User
from app.schemas import UserCreate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: DbSession):
    user = User(**payload.model_dump())
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # Let the unique constraint decide, instead of checking first: a
        # check-then-insert races when two requests pick the same name at once.
        db.rollback()
        if getattr(exc.orig.diag, "constraint_name", None) == "uq_users_username":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{payload.username}' is already taken",
            )
        raise
    db.refresh(user)  # load server-set values (id, created_at)
    return user


@router.get("", response_model=list[UserResponse])
def list_users(db: DbSession, limit: Limit = 50, offset: Offset = 0):
    # Used by the frontend's demo-user picker (there is no authentication yet).
    stmt = select(User).order_by(User.id).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user: ExistingUser):
    return user
