"""Turning text into vectors, so that similar meanings end up close together.

Everything else depends on the small Embedder protocol, which keeps the model replaceable
and lets tests run without downloading one. If the model cannot load, get_embedder returns
None and search falls back to keywords.
"""

import logging
from functools import lru_cache
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Experience

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384 dimensions, English, ~70 MB, runs on CPU via ONNX


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    name = MODEL_NAME

    def __init__(self) -> None:
        from fastembed import TextEmbedding  # imported here: slow, and only needed for search

        self._model = TextEmbedding(MODEL_NAME)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


@lru_cache(maxsize=1)
def get_embedder() -> Embedder | None:
    """The shared model, loaded on first use. None means semantic search is unavailable."""
    try:
        return FastEmbedder()
    except Exception:
        logger.exception("Could not load embedding model %s; search will use keywords only", MODEL_NAME)
        return None


def experience_text(exp: Experience) -> str:
    return f"{exp.title}. {exp.category}. {exp.description}"


def embed_missing(db: Session, embedder: Embedder, force: bool = False) -> int:
    """Embed experiences with no vector, or one from another model. Returns how many changed."""
    stmt = select(Experience).order_by(Experience.id)
    if not force:
        stmt = stmt.where(or_(Experience.embedding.is_(None), Experience.embedding_model != embedder.name))
    experiences = db.scalars(stmt).all()
    if experiences:
        vectors = embedder.embed_documents([experience_text(e) for e in experiences])
        for experience, vector in zip(experiences, vectors):
            experience.embedding = vector
            experience.embedding_model = embedder.name
        db.commit()
    return len(experiences)
