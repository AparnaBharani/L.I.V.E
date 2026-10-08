"""HTTP tests for /users/{user_id}/interactions."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.enums import EventType
from app.models import Interaction

NON_SEARCH_EVENTS = [e for e in EventType if e is not EventType.SEARCH]


def url(user_id: int) -> str:
    return f"/users/{user_id}/interactions"


def stored_events(db_session, user_id: int) -> list[Interaction]:
    stmt = select(Interaction).where(Interaction.user_id == user_id).order_by(Interaction.id)
    return list(db_session.scalars(stmt))


class TestCreateInteraction:
    def test_creates_non_search_event(self, client, db_session, user, experience):
        response = client.post(url(user.id), json={"event_type": "save", "experience_id": experience.id})

        assert response.status_code == 201
        body = response.json()
        assert body["user_id"] == user.id
        assert body["experience_id"] == experience.id
        assert body["event_type"] == "save"
        assert body["query_text"] is None
        assert body["occurred_at"]

        [row] = stored_events(db_session, user.id)
        assert row.id == body["id"] and row.event_type == "save"

    def test_creates_search_event_without_experience(self, client, db_session, user):
        response = client.post(url(user.id), json={"event_type": "search", "query_text": "  weekend hikes "})

        assert response.status_code == 201
        assert response.json()["experience_id"] is None
        assert response.json()["query_text"] == "weekend hikes"  # whitespace trimmed

        [row] = stored_events(db_session, user.id)
        assert row.experience_id is None and row.query_text == "weekend hikes"

    @pytest.mark.parametrize("event_type", NON_SEARCH_EVENTS)
    def test_every_non_search_event_type_accepted(self, client, user, experience, event_type):
        response = client.post(url(user.id), json={"event_type": event_type, "experience_id": experience.id})

        assert response.status_code == 201
        assert response.json()["event_type"] == event_type

    def test_properties_round_trip(self, client, db_session, user, experience):
        props = {"source": "home_feed", "position": 3, "score": 0.82, "from_search": False}

        response = client.post(
            url(user.id), json={"event_type": "view", "experience_id": experience.id, "properties": props}
        )

        assert response.status_code == 201
        assert response.json()["properties"] == props
        assert stored_events(db_session, user.id)[0].properties == props


class TestUserIdComesFromUrl:
    def test_user_id_in_body_is_rejected(self, client, db_session, make_user, experience):
        alice, bob = make_user("alice"), make_user("bob")

        # Alice's URL, but the body claims to be Bob.
        response = client.post(
            url(alice.id),
            json={"event_type": "like", "experience_id": experience.id, "user_id": bob.id},
        )

        assert response.status_code == 422
        assert stored_events(db_session, alice.id) == []
        assert stored_events(db_session, bob.id) == []

    def test_event_is_stored_for_the_url_user_only(self, client, db_session, make_user, experience):
        alice, bob = make_user("alice"), make_user("bob")

        client.post(url(alice.id), json={"event_type": "like", "experience_id": experience.id})

        assert [e.user_id for e in stored_events(db_session, alice.id)] == [alice.id]
        assert stored_events(db_session, bob.id) == []

    @pytest.mark.parametrize("field, value", [("id", 1), ("occurred_at", "2026-01-01T00:00:00Z")])
    def test_other_server_controlled_fields_rejected(self, client, db_session, user, experience, field, value):
        response = client.post(
            url(user.id), json={"event_type": "view", "experience_id": experience.id, field: value}
        )

        assert response.status_code == 422
        assert stored_events(db_session, user.id) == []


class TestInvalidInteractions:
    @pytest.mark.parametrize(
        "body, message",
        [
            ({"event_type": "search"}, "search events require query_text"),
            ({"event_type": "search", "query_text": "   "}, "at least 1 character"),
            ({"event_type": "search", "query_text": "q", "experience_id": 1}, "must not include experience_id"),
            ({"event_type": "view"}, "view events require experience_id"),
            ({"event_type": "view", "experience_id": 1, "query_text": "q"}, "only allowed for search events"),
            ({"event_type": "start", "experience_id": 1}, "Input should be"),
            ({"experience_id": 1}, "Field required"),
            ({"event_type": "view", "experience_id": "1"}, "valid integer"),
            ({"event_type": "view", "experience_id": 1, "properties": {"a": {"b": 1}}}, "valid string"),
        ],
    )
    def test_returns_422_and_writes_nothing(self, client, db_session, user, body, message):
        response = client.post(url(user.id), json=body)

        assert response.status_code == 422
        assert message in str(response.json()["detail"])
        assert stored_events(db_session, user.id) == []

    def test_nonexistent_user_returns_404(self, client, experience, nonexistent_id):
        response = client.post(url(nonexistent_id), json={"event_type": "view", "experience_id": experience.id})

        assert response.status_code == 404
        assert response.json()["detail"] == f"User {nonexistent_id} not found"

    @pytest.mark.parametrize("event_type", NON_SEARCH_EVENTS)
    def test_nonexistent_experience_returns_404(self, client, db_session, user, nonexistent_id, event_type):
        response = client.post(url(user.id), json={"event_type": event_type, "experience_id": nonexistent_id})

        assert response.status_code == 404
        assert response.json()["detail"] == f"Experience {nonexistent_id} not found"
        assert stored_events(db_session, user.id) == []

    def test_unknown_user_is_reported_before_invalid_body(self, client, nonexistent_id):
        # FastAPI resolves dependencies (ExistingUser) before reporting body errors.
        response = client.post(url(nonexistent_id), json={"event_type": "view"})
        assert response.status_code == 404


class TestListInteractions:
    @pytest.fixture
    def add_event(self, db_session, user, experience):
        """Insert an event directly with a chosen occurred_at, so ordering is testable.

        (Through the API every event in one test would get the same timestamp:
        now() is the transaction start time, and each test is one transaction.)
        """

        def _add(minutes_ago: int, event_type: str = "view") -> Interaction:
            event = Interaction(
                user_id=user.id,
                experience_id=experience.id,
                event_type=event_type,
                occurred_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
            )
            db_session.add(event)
            db_session.flush()
            return event

        return _add

    def test_returns_users_events(self, client, user, experience):
        client.post(url(user.id), json={"event_type": "view", "experience_id": experience.id})
        client.post(url(user.id), json={"event_type": "search", "query_text": "hikes"})

        response = client.get(url(user.id))

        assert response.status_code == 200
        assert sorted(e["event_type"] for e in response.json()) == ["search", "view"]
        assert all(e["user_id"] == user.id for e in response.json())

    def test_newest_first_by_occurred_at_not_id(self, client, user, add_event):
        # Inserted out of time order: the highest id is NOT the newest event.
        middle = add_event(minutes_ago=10)
        newest = add_event(minutes_ago=1)
        oldest = add_event(minutes_ago=60)

        ids = [e["id"] for e in client.get(url(user.id)).json()]

        assert ids == [newest.id, middle.id, oldest.id]

    def test_same_timestamp_ties_broken_by_id_desc(self, client, user, experience):
        # Same transaction -> same now() -> same occurred_at for both.
        first = client.post(url(user.id), json={"event_type": "view", "experience_id": experience.id}).json()
        second = client.post(url(user.id), json={"event_type": "save", "experience_id": experience.id}).json()
        assert first["occurred_at"] == second["occurred_at"]

        ids = [e["id"] for e in client.get(url(user.id)).json()]

        assert ids == [second["id"], first["id"]]

    def test_pagination(self, client, user, add_event):
        events = [add_event(minutes_ago=m) for m in (1, 2, 3, 4, 5)]  # newest first already

        page = client.get(url(user.id), params={"limit": 2, "offset": 2}).json()

        assert [e["id"] for e in page] == [events[2].id, events[3].id]

    def test_only_this_users_events(self, client, make_user, experience):
        alice, bob = make_user("alice"), make_user("bob")
        client.post(url(bob.id), json={"event_type": "like", "experience_id": experience.id})

        assert client.get(url(alice.id)).json() == []

    def test_nonexistent_user_returns_404(self, client, nonexistent_id):
        assert client.get(url(nonexistent_id)).status_code == 404

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
    def test_invalid_pagination_returns_422(self, client, user, params):
        assert client.get(url(user.id), params=params).status_code == 422
