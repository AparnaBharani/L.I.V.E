"""HTTP tests for /users."""

import pytest
from sqlalchemy import select

from app.models import User


class TestCreateUser:
    def test_creates_user(self, client, db_session):
        response = client.post("/users", json={"username": "aparna"})

        assert response.status_code == 201
        body = response.json()
        assert body["username"] == "aparna"
        assert isinstance(body["id"], int)
        assert body["created_at"]  # set by the database, not the client

        stored = db_session.scalars(select(User).where(User.username == "aparna")).one()
        assert stored.id == body["id"]

    def test_duplicate_username_returns_409(self, client, make_user):
        make_user("taken_name")

        response = client.post("/users", json={"username": "taken_name"})

        assert response.status_code == 409
        assert "already taken" in response.json()["detail"]

    def test_session_still_usable_after_409(self, client, make_user):
        # The route rolls back after the IntegrityError; later requests must still work.
        make_user("taken_name")
        assert client.post("/users", json={"username": "taken_name"}).status_code == 409

        assert client.post("/users", json={"username": "fresh_name"}).status_code == 201

    @pytest.mark.parametrize(
        "body",
        [
            {},                                # missing username
            {"username": "ab"},                # too short
            {"username": "has space"},         # bad characters
            {"username": "x" * 51},            # too long
            {"username": 123},                 # wrong type
            {"username": "ok_name", "id": 1},  # server-controlled field
        ],
    )
    def test_invalid_body_returns_422(self, client, db_session, body):
        response = client.post("/users", json=body)

        assert response.status_code == 422
        assert db_session.scalars(select(User)).all() == []  # nothing was written


class TestListUsers:
    def test_lists_users_in_id_order(self, client, make_user):
        created = [make_user().id for _ in range(3)]

        response = client.get("/users", params={"limit": 100})

        assert response.status_code == 200
        ids = [u["id"] for u in response.json()]
        assert [i for i in ids if i in created] == created
        assert ids == sorted(ids)

    def test_pagination(self, client, make_user):
        for _ in range(4):
            make_user()
        all_ids = [u["id"] for u in client.get("/users", params={"limit": 100}).json()]

        page = client.get("/users", params={"limit": 2, "offset": 1}).json()

        assert [u["id"] for u in page] == all_ids[1:3]

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
    def test_invalid_pagination_returns_422(self, client, params):
        assert client.get("/users", params=params).status_code == 422


class TestGetUser:
    def test_returns_user(self, client, user):
        response = client.get(f"/users/{user.id}")

        assert response.status_code == 200
        assert response.json()["id"] == user.id
        assert response.json()["username"] == user.username

    def test_nonexistent_user_returns_404(self, client, nonexistent_id):
        response = client.get(f"/users/{nonexistent_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == f"User {nonexistent_id} not found"

    @pytest.mark.parametrize("bad_id", ["abc", "1.5"])
    def test_invalid_path_parameter_returns_422(self, client, bad_id):
        assert client.get(f"/users/{bad_id}").status_code == 422
