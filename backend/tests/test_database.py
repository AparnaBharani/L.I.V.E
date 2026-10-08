"""Database-level tests: what PostgreSQL itself guarantees, independent of the API."""

import re

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.database import engine
from app.enums import EventType
from app.models import Interaction, User


def insert_raw_interaction(db_session, **values):
    """Bypass Pydantic and the API entirely, so only the database's rules apply."""
    columns = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    db_session.execute(text(f"INSERT INTO interactions ({columns}) VALUES ({params})"), values)


def assert_rejected_by(db_session, constraint: str, **values):
    with pytest.raises(IntegrityError) as exc:
        with db_session.begin_nested():  # SAVEPOINT, so the test transaction survives the error
            insert_raw_interaction(db_session, **values)
    assert exc.value.orig.diag.constraint_name == constraint


class TestIsolation:
    def test_tests_use_the_test_database(self, db_session):
        name = db_session.execute(text("SELECT current_database()")).scalar()
        assert name.endswith("_test") and name != "live_db"

    def test_app_engine_points_at_the_test_database(self):
        assert engine.url.database.endswith("_test")

    def test_schema_matches_migrations(self, db_session):
        tables = set(inspect(db_session.connection()).get_table_names())
        assert tables == {"alembic_version", "users", "experiences", "interactions"}
        version = db_session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version  # schema was built by Alembic, not create_all()


class TestApiWritesReachTheDatabase:
    def test_full_flow_is_stored_with_relationships(self, client, db_session):
        user_id = client.post("/users", json={"username": "flow_user"}).json()["id"]
        exp_id = client.post(
            "/experiences",
            json={"title": "Sunrise hike", "description": "d", "category": "outdoors",
                  "difficulty": "beginner", "duration_minutes": 60},
        ).json()["id"]
        client.post(f"/users/{user_id}/interactions", json={"event_type": "save", "experience_id": exp_id})
        client.post(f"/users/{user_id}/interactions", json={"event_type": "search", "query_text": "hikes"})

        # JOIN through the foreign keys: each event resolves to a real user and experience.
        rows = db_session.execute(text("""
            SELECT u.username, i.event_type, e.title, i.query_text
            FROM interactions i
            JOIN users u ON u.id = i.user_id
            LEFT JOIN experiences e ON e.id = i.experience_id
            WHERE i.user_id = :u
            ORDER BY i.id
        """), {"u": user_id}).all()

        assert [tuple(r) for r in rows] == [
            ("flow_user", "save", "Sunrise hike", None),
            ("flow_user", "search", None, "hikes"),
        ]

    def test_properties_stored_as_queryable_jsonb(self, client, db_session, user, experience):
        client.post(
            f"/users/{user.id}/interactions",
            json={"event_type": "view", "experience_id": experience.id,
                  "properties": {"source": "home_feed", "position": 3}},
        )

        # ->> and -> are PostgreSQL JSONB operators: this only works on real JSONB.
        source, position = db_session.execute(text(
            "SELECT properties->>'source', (properties->'position')::int FROM interactions WHERE user_id = :u"
        ), {"u": user.id}).one()
        assert (source, position) == ("home_feed", 3)


class TestConstraints:
    def test_check_constraint_matches_python_event_types(self, db_session):
        checks = inspect(db_session.connection()).get_check_constraints("interactions")
        sql = next(c["sqltext"] for c in checks if c["name"] == "ck_interactions_event_type_valid")
        assert set(re.findall(r"'(\w+)'", sql)) == {e.value for e in EventType}

    def test_search_allows_query_without_experience(self, db_session, user):
        insert_raw_interaction(db_session, user_id=user.id, event_type="search", query_text="hikes")
        row = db_session.scalars(select(Interaction).where(Interaction.user_id == user.id)).one()
        assert row.experience_id is None

    def test_non_search_event_must_reference_experience(self, db_session, user):
        assert_rejected_by(db_session, "ck_interactions_event_shape", user_id=user.id, event_type="view")

    def test_non_search_event_must_not_have_query(self, db_session, user, experience):
        assert_rejected_by(db_session, "ck_interactions_event_shape",
                           user_id=user.id, experience_id=experience.id, event_type="view", query_text="q")

    def test_unknown_event_type_rejected(self, db_session, user, experience):
        assert_rejected_by(db_session, "ck_interactions_event_type_valid",
                           user_id=user.id, experience_id=experience.id, event_type="start")

    def test_foreign_key_to_experience(self, db_session, user, nonexistent_id):
        assert_rejected_by(db_session, "fk_interactions_experience_id_experiences",
                           user_id=user.id, experience_id=nonexistent_id, event_type="view")

    def test_foreign_key_to_user(self, db_session, experience, nonexistent_id):
        assert_rejected_by(db_session, "fk_interactions_user_id_users",
                           user_id=nonexistent_id, experience_id=experience.id, event_type="view")

    def test_deleting_user_cascades_to_their_events(self, db_session, user, experience):
        insert_raw_interaction(db_session, user_id=user.id, experience_id=experience.id, event_type="view")
        db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": user.id})
        remaining = db_session.execute(
            text("SELECT count(*) FROM interactions WHERE user_id = :u"), {"u": user.id}
        ).scalar()
        assert remaining == 0

    def test_username_unique(self, db_session, make_user):
        make_user("same_name")
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.add(User(username="same_name"))
                db_session.flush()
