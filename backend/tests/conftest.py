"""Shared pytest setup: an isolated PostgreSQL test database and per-test transactions.

How the tests stay away from live_db:
  1. TEST_DATABASE_URL must be set (environment variable or backend/.env).
     There is deliberately NO fallback to DATABASE_URL.
  2. Its database name must end in "_test" and differ from DATABASE_URL's.
  3. Before the app is imported, DATABASE_URL is replaced by TEST_DATABASE_URL,
     so the app's own engine is created against the test database.

How tests stay isolated from each other:
  - Once per run: the test database is dropped, recreated and migrated with Alembic.
  - Once per test: everything runs inside one transaction that is rolled back.
"""

import itertools
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_test_database_url() -> str:
    env_file = dotenv_values(BACKEND_DIR / ".env")
    test_url = os.environ.get("TEST_DATABASE_URL") or env_file.get("TEST_DATABASE_URL")
    dev_url = os.environ.get("DATABASE_URL") or env_file.get("DATABASE_URL")

    if not test_url:
        pytest.exit(
            "TEST_DATABASE_URL is not set (see backend/.env.example). "
            "Refusing to run tests rather than risk using the development database.",
            returncode=1,
        )
    test_db = make_url(test_url).database or ""
    if not test_db.endswith("_test"):
        pytest.exit(f"TEST_DATABASE_URL database '{test_db}' must end in '_test'.", returncode=1)
    if dev_url and make_url(dev_url).database == test_db:
        pytest.exit("TEST_DATABASE_URL must not point at the DATABASE_URL database.", returncode=1)
    return test_url


TEST_DATABASE_URL = _load_test_database_url()
TEST_DATABASE_NAME = make_url(TEST_DATABASE_URL).database

# Must happen BEFORE anything imports app.config: app.database builds its engine
# from settings.DATABASE_URL at import time, and real environment variables take
# priority over values in .env.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Only now is it safe to import the application.
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.database import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Experience, User  # noqa: E402

assert engine.url.database == TEST_DATABASE_NAME, "app engine is not using the test database"


@pytest.fixture(scope="session")
def test_database():
    """Once per pytest run: fresh test database, schema built by the real migrations."""
    admin_url = make_url(TEST_DATABASE_URL).set(database="postgres")
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))
    admin.dispose()

    # alembic/env.py reads settings.DATABASE_URL, which now points at the test database.
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    yield

    assert engine.pool.checkedout() == 0, "a test leaked a database connection"
    engine.dispose()


@pytest.fixture
def db_session(test_database):
    """A session whose work is always rolled back at the end of the test.

    The routes call db.commit(). With join_transaction_mode="create_savepoint"
    that commit only releases a SAVEPOINT inside our outer transaction, and the
    outer transaction is rolled back below, so nothing is ever kept.
    """
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """An HTTP client for the app, wired to the test's db_session instead of get_db."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------- test data ----------
# Created directly through the session (not the API), so tests for one endpoint
# don't depend on another endpoint working. flush() sends the INSERT so the row
# has an id and is visible to the API, which uses the same session.

@pytest.fixture
def make_user(db_session):
    counter = itertools.count(1)

    def _make_user(username: str | None = None) -> User:
        user = User(username=username or f"test_user_{next(counter)}")
        db_session.add(user)
        db_session.flush()
        return user

    return _make_user


@pytest.fixture
def make_experience(db_session):
    def _make_experience(**overrides) -> Experience:
        fields = {
            "title": "Sunrise hike",
            "description": "A gentle 5 km walk to the hilltop.",
            "category": "outdoors",
            "difficulty": "beginner",
            "duration_minutes": 120,
            **overrides,
        }
        experience = Experience(**fields)
        db_session.add(experience)
        db_session.flush()
        return experience

    return _make_experience


@pytest.fixture
def user(make_user) -> User:
    return make_user()


@pytest.fixture
def experience(make_experience) -> Experience:
    return make_experience()


@pytest.fixture
def nonexistent_id() -> int:
    # Largest PostgreSQL INTEGER: a valid id that no sequence will reach in tests.
    return 2_147_483_647
