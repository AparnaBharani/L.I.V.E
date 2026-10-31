"""Generate embeddings for experiences that lack one. Safe to re-run.

Run from backend/ after seeding or adding experiences:
    python -m scripts.embed_experiences
    python -m scripts.embed_experiences --force    # re-embed everything

It writes only the embedding columns of experiences in DATABASE_URL.
"""

import argparse
import sys

from sqlalchemy.engine import make_url

from app.config import settings
from app.database import SessionLocal
from app.search.embedding import MODEL_NAME, embed_missing, get_embedder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-embed every experience")
    args = parser.parse_args()

    embedder = get_embedder()
    if embedder is None:
        sys.exit(f"Could not load {MODEL_NAME}. Search will keep working with keywords only.")
    with SessionLocal() as db:
        count = embed_missing(db, embedder, force=args.force)
    print(f"Embedded {count} experiences in '{make_url(settings.DATABASE_URL).database}' with {MODEL_NAME}")


if __name__ == "__main__":
    main()
