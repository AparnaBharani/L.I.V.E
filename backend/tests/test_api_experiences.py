"""HTTP tests for /experiences."""

import pytest
from sqlalchemy import select

from app.models import Experience

VALID = {
    "title": "Pottery class",
    "description": "Two hours at the wheel.",
    "category": "creative",
    "difficulty": "beginner",
    "duration_minutes": 120,
    "cost": 800,
}


class TestCreateExperience:
    def test_creates_experience(self, client, db_session):
        response = client.post("/experiences", json=VALID)

        assert response.status_code == 201
        body = response.json()
        assert {k: body[k] for k in VALID} == VALID
        assert isinstance(body["id"], int)
        assert body["created_at"]

        stored = db_session.get(Experience, body["id"])
        assert stored is not None and stored.title == "Pottery class"

    def test_cost_defaults_to_zero(self, client):
        body = {k: v for k, v in VALID.items() if k != "cost"}
        assert client.post("/experiences", json=body).json()["cost"] == 0

    @pytest.mark.parametrize(
        "override",
        [
            {"title": "   "},                     # blank after trimming
            {"title": "x" * 201},                 # too long
            {"duration_minutes": 0},              # must be positive
            {"duration_minutes": "120"},          # string, not integer
            {"cost": -1},                         # negative
            {"created_at": "2026-01-01T00:00:00Z"},  # server-controlled
            {"id": 1},                            # server-controlled
        ],
    )
    def test_invalid_fields_return_422(self, client, db_session, override):
        response = client.post("/experiences", json={**VALID, **override})

        assert response.status_code == 422
        assert db_session.scalars(select(Experience)).all() == []

    def test_missing_field_returns_422(self, client):
        body = {k: v for k, v in VALID.items() if k != "title"}
        assert client.post("/experiences", json=body).status_code == 422


class TestListExperiences:
    def test_lists_experiences_in_id_order(self, client, make_experience):
        created = [make_experience(title=f"Experience {i}").id for i in range(3)]

        response = client.get("/experiences", params={"limit": 100})

        assert response.status_code == 200
        ids = [e["id"] for e in response.json()]
        assert [i for i in ids if i in created] == created
        assert ids == sorted(ids)

    def test_pagination_with_limit_and_offset(self, client, make_experience):
        for i in range(5):
            make_experience(title=f"Experience {i}")
        all_ids = [e["id"] for e in client.get("/experiences", params={"limit": 100}).json()]

        page = client.get("/experiences", params={"limit": 2, "offset": 1}).json()

        assert [e["id"] for e in page] == all_ids[1:3]

    def test_offset_past_the_end_returns_empty_list(self, client, make_experience):
        make_experience()
        response = client.get("/experiences", params={"offset": 1_000_000})
        assert response.status_code == 200 and response.json() == []

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "x"}])
    def test_invalid_pagination_returns_422(self, client, params):
        assert client.get("/experiences", params=params).status_code == 422


class TestGetExperience:
    def test_returns_experience(self, client, experience):
        response = client.get(f"/experiences/{experience.id}")

        assert response.status_code == 200
        assert response.json()["title"] == experience.title

    def test_nonexistent_experience_returns_404(self, client, nonexistent_id):
        response = client.get(f"/experiences/{nonexistent_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == f"Experience {nonexistent_id} not found"

    @pytest.mark.parametrize("bad_id", ["abc", "1.5"])
    def test_invalid_path_parameter_returns_422(self, client, bad_id):
        assert client.get(f"/experiences/{bad_id}").status_code == 422
