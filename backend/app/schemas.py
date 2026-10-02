"""API contracts: what clients may send (requests) and what we promise to return (responses).

Request schemas validate untrusted input. Response schemas only describe output;
they deliberately carry no input rules, so tightening a request rule later can
never make existing rows fail to serialise.
"""

from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.enums import EventType


class RequestSchema(BaseModel):
    # extra="forbid": unknown fields (e.g. a client-sent "id" or "occurred_at")
    # are rejected instead of silently ignored.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseSchema(BaseModel):
    # from_attributes: build the response by reading attributes of an ORM object.
    model_config = ConfigDict(from_attributes=True)


# strict=True: only real integers. Without it, "120" (a string) and true (a bool)
# would be silently converted to numbers.
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]


# ---------- Experience ----------

class ExperienceCreate(RequestSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    category: str = Field(min_length=1, max_length=50)
    difficulty: str = Field(min_length=1, max_length=50)
    duration_minutes: PositiveInt
    cost: NonNegativeInt = 0


class ExperienceResponse(ResponseSchema):
    id: int
    title: str
    description: str
    category: str
    difficulty: str
    duration_minutes: int
    cost: int
    created_at: datetime


# ---------- User ----------

class UserCreate(RequestSchema):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_]+$")


class UserResponse(ResponseSchema):
    id: int
    username: str
    created_at: datetime


# ---------- Interaction ----------

# properties is a small, flat bag of scalars, e.g. {"source": "home_feed", "position": 3}.
# Flat keeps it easy to query later; the limits stop clients storing arbitrary blobs.
PropertyKey = Annotated[str, StringConstraints(min_length=1, max_length=50)]
PropertyValue = Annotated[str, StringConstraints(max_length=200)] | int | float | bool


class InteractionCreate(RequestSchema):
    """One event, as sent by the client.

    There is no user_id: who performed the event is identity, not event data.
    For now it comes from the URL; in V8 it will come from authentication.
    id and occurred_at are always set by the server.
    """

    event_type: EventType
    experience_id: PositiveInt | None = None
    query_text: str | None = Field(default=None, min_length=1, max_length=500)
    properties: dict[PropertyKey, PropertyValue] | None = Field(default=None, max_length=20)

    # Mirrors ck_interactions_event_shape in the database.
    @model_validator(mode="after")
    def check_event_shape(self) -> Self:
        if self.event_type == EventType.SEARCH:
            if self.query_text is None:
                raise ValueError("search events require query_text")
            if self.experience_id is not None:
                raise ValueError("search events must not include experience_id")
        else:
            if self.experience_id is None:
                raise ValueError(f"{self.event_type.value} events require experience_id")
            if self.query_text is not None:
                raise ValueError("query_text is only allowed for search events")
        return self


class InteractionResponse(ResponseSchema):
    id: int
    user_id: int
    experience_id: int | None
    event_type: EventType
    query_text: str | None
    properties: dict[str, Any] | None
    occurred_at: datetime
