"""Inputs and failures that must produce a clean HTTP error, never an unhandled 500."""

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app


class TestHostileInput:
    @pytest.mark.parametrize("path", [
        "/users?offset=99999999999999999999999",
        "/experiences?offset=99999999999999999999999",
    ])
    def test_absurd_offset_is_rejected(self, client, path):
        assert client.get(path).status_code == 422

    @pytest.mark.parametrize("path", [
        "/users/99999999999999999999999",
        "/experiences/99999999999999999999999",
        "/users/99999999999999999999999/interactions",
        "/users/99999999999999999999999/recommendations",
    ])
    def test_id_beyond_database_range_is_not_a_crash(self, client, path):
        assert client.get(path).status_code in (404, 422)

    def test_experience_id_beyond_database_range_is_not_a_crash(self, client, user):
        response = client.post(f"/users/{user.id}/interactions",
                               json={"event_type": "view", "experience_id": 10**30})
        assert response.status_code in (404, 422)

    @pytest.mark.parametrize("body", [
        {"event_type": "search", "query_text": "hik\u0000es"},
        {"event_type": "search", "query_text": "hikes", "properties": {"source": "a\u0000b"}},
        {"event_type": "search", "query_text": "hikes", "properties": {"a\u0000b": "source"}},
    ])
    def test_nul_characters_are_rejected(self, client, user, body):
        # PostgreSQL text cannot store NUL; it must be a 422, not a driver crash.
        assert client.post(f"/users/{user.id}/interactions", json=body).status_code == 422

    def test_nul_in_username_is_rejected(self, client):
        assert client.post("/users", json={"username": "abc\u0000"}).status_code == 422


class TestDatabaseFailure:
    def test_database_outage_is_a_503_the_client_can_read(self, client):
        def broken_db():
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
            yield

        app.dependency_overrides[get_db] = broken_db
        response = client.get("/experiences", headers={"Origin": "http://localhost:3000"})

        assert response.status_code == 503
        assert response.json() == {"detail": "The database is unavailable. Please try again shortly."}
        # Without CORS headers the browser would hide this message from the frontend.
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


class TestExperienceDeletedMidRequest:
    def test_foreign_key_race_is_a_404(self, client, db_session, user, experience, monkeypatch):
        # The existence check passes, then the row disappears before the INSERT.
        real_get_or_404 = __import__("app.routers.interactions", fromlist=["get_or_404"]).get_or_404
        calls = []

        def vanishing(db, model, obj_id):
            calls.append(obj_id)
            if len(calls) == 1:
                found = real_get_or_404(db, model, obj_id)
                db.delete(found)
                db.flush()
                return found
            return real_get_or_404(db, model, obj_id)

        monkeypatch.setattr("app.routers.interactions.get_or_404", vanishing)
        response = client.post(f"/users/{user.id}/interactions",
                               json={"event_type": "view", "experience_id": experience.id})

        assert response.status_code == 404
