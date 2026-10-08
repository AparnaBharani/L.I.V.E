"""Small building blocks shared by the routers."""

from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import User

# Writing `db: DbSession` in a route means "FastAPI, call get_db() and give me the session".
# Within one request FastAPI calls get_db only once, so every dependency shares the same session.
DbSession = Annotated[Session, Depends(get_db)]

# Pagination for list endpoints, e.g. GET /experiences?limit=20&offset=40
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

ModelT = TypeVar("ModelT", bound=Base)


def get_or_404(db: Session, model: type[ModelT], obj_id: int) -> ModelT:
    """Primary-key lookup (SELECT ... WHERE id = :id) that turns "no row" into HTTP 404."""
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} {obj_id} not found",
        )
    return obj


def get_existing_user(user_id: int, db: DbSession) -> User:
    # FastAPI fills user_id from the path parameter of the same name.
    return get_or_404(db, User, user_id)


ExistingUser = Annotated[User, Depends(get_existing_user)]
