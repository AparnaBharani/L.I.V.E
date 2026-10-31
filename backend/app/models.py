from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.enums import EventType

EVENT_TYPE_VALUES = ", ".join(f"'{e.value}'" for e in EventType)


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    difficulty: Mapped[str] = mapped_column(String)
    duration_minutes: Mapped[int]
    cost: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Search columns are deferred: most queries never read them, and vectors are large.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english'::regconfig, title), 'A') || "
            "setweight(to_tsvector('english'::regconfig, category), 'B') || "
            "setweight(to_tsvector('english'::regconfig, description), 'C')",
            persisted=True,
        ),
        deferred=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), deferred=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        Index("ix_experiences_search_vector", "search_vector", postgresql_using="gin"),
    )


class User(Base):
    __tablename__ = "users"  # "user" is a reserved word in PostgreSQL

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Interaction(Base):
    """One row per user action. Rows are appended, never updated."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    # Nullable because a search is not about one specific experience.
    experience_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiences.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(32))
    # The search text, for search events only.
    query_text: Mapped[str | None] = mapped_column(Text)
    # Event-specific details that don't deserve their own column yet,
    # e.g. {"source": "home_feed", "position": 3}.
    properties: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(f"event_type IN ({EVENT_TYPE_VALUES})", name="event_type_valid"),
        # Search events carry a query and no experience; every other event
        # is about exactly one experience and carries no query.
        CheckConstraint(
            "(event_type = 'search' AND query_text IS NOT NULL AND experience_id IS NULL)"
            " OR (event_type <> 'search' AND experience_id IS NOT NULL AND query_text IS NULL)",
            name="event_shape",
        ),
        # "Show me this user's history, newest first" (personalization).
        Index("ix_interactions_user_id_occurred_at", "user_id", "occurred_at"),
        # "How many saves/likes does this experience have?" (popularity).
        Index("ix_interactions_experience_id_event_type", "experience_id", "event_type"),
    )
