"""Run the backend for Playwright against a disposable, freshly seeded database.

Started by frontend/playwright.config.ts. On every run it DROPS and recreates
`live_db_e2e`, applies the migrations, seeds the demo data and serves the API.

Safety, mirroring tests/conftest.py:
  - The target is derived from TEST_DATABASE_URL with the database name replaced,
    so it can never fall back to DATABASE_URL.
  - It refuses any database whose name does not end in "_e2e".
  - DATABASE_URL is replaced BEFORE the app is imported, so the app's own engine
    can only reach the disposable database.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent
E2E_DATABASE = "live_db_e2e"
HOST, PORT = "127.0.0.1", 8000


def e2e_database_url(test_url: str | None) -> str:
    if not test_url:
        sys.exit("TEST_DATABASE_URL is not set (see backend/.env.example).")
    return make_url(test_url).set(database=E2E_DATABASE).render_as_string(hide_password=False)


def check_disposable(url: str) -> str:
    """Return the database name, or exit unless it is explicitly disposable."""
    name = make_url(url).database or ""
    if not name.endswith("_e2e"):
        sys.exit(f"Refusing to recreate '{name}': only '*_e2e' databases are disposable.")
    return name


def recreate_database(url: str) -> None:
    name = check_disposable(url)
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


def main() -> None:
    env_file = dotenv_values(BACKEND_DIR / ".env")
    url = e2e_database_url(os.environ.get("TEST_DATABASE_URL") or env_file.get("TEST_DATABASE_URL"))
    recreate_database(url)

    # Must happen BEFORE anything imports app.config.
    os.environ["DATABASE_URL"] = url

    import uvicorn
    from alembic import command
    from alembic.config import Config

    from app.database import SessionLocal
    from scripts.seed import seed

    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    with SessionLocal() as db:
        print("seeded:", seed(db, now=datetime.now(timezone.utc)))

    uvicorn.run("app.main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
