"""HTTP tests for GET /users/{user_id}/recommendations (isolated test database)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Interaction

CATEGORIES = ["outdoors", "creative", "wellness", "social", "learning", "adventure"]


@pytest.fixture
def catalogue(make_experience):
    """4 experiences per category, identical apart from category, so only behaviour matters."""
    return {
        cat: [make_experience(title=f"{cat} {i}", category=cat) for i in range(4)]
        for cat in CATEGORIES
    }


@pytest.fixture
def add_events(db_session):
    def _add(user, *events):
        """events: (experience, event_type, days_ago)"""
        now = datetime.now(timezone.utc)
        for experience, event_type, days_ago in events:
            db_session.add(Interaction(user_id=user.id, experience_id=experience.id,
                                       event_type=event_type, occurred_at=now - timedelta(days=days_ago)))
        db_session.flush()
    return _add


def fan_of(add_events, user, experiences, start_day=10):
    """A believable history: view → save → like for each experience, spread over days."""
    add_events(user, *[(e, t, start_day - i) for i, e in enumerate(experiences) for t in ("view", "save", "like")])


def recs(client, user, **params):
    response = client.get(f"/users/{user.id}/recommendations", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def categories(body, n=3):
    return [item["experience"]["category"] for item in body["items"][:n]]


class TestPersonalisation:
    @pytest.mark.parametrize("category", ["outdoors", "creative", "wellness"])
    def test_focused_user_gets_their_category_first(self, client, make_user, catalogue, add_events, category):
        user = make_user()
        fan_of(add_events, user, catalogue[category][:2])

        body = recs(client, user)

        assert body["strategy"] == "personalized"
        assert categories(body, 1) == [category]
        assert f"matches your interest in {category}" in body["items"][0]["reasons"]

    def test_different_users_get_different_recommendations(self, client, make_user, catalogue, add_events):
        outdoor, creative, cold = make_user(), make_user(), make_user()
        fan_of(add_events, outdoor, catalogue["outdoors"][:2])
        fan_of(add_events, creative, catalogue["creative"][:2])

        lists = [[i["experience"]["id"] for i in recs(client, u)["items"][:5]] for u in (outdoor, creative, cold)]

        assert lists[0] != lists[1] and lists[1] != lists[2] and lists[0] != lists[2]

    def test_new_interaction_changes_recommendations(self, client, make_user, catalogue):
        # Closing the loop through the public API only: event in → different ranking out.
        user = make_user()
        for e in catalogue["wellness"][:2]:
            for t in ("view", "save", "like", "complete"):
                assert client.post(f"/users/{user.id}/interactions",
                                   json={"event_type": t, "experience_id": e.id}).status_code == 201

        body = recs(client, user)

        assert categories(body, 1) == ["wellness"]
        returned = {i["experience"]["id"] for i in body["items"]}
        assert not returned & {e.id for e in catalogue["wellness"][:2]}  # completed → excluded


class TestColdStart:
    def test_user_without_history_gets_fallback(self, client, user, catalogue):
        body = recs(client, user)

        assert body["strategy"] == "cold_start"
        assert len(body["items"]) == 10
        assert all(set(i["features"]) == {"popularity", "freshness"} for i in body["items"])
        assert len(set(categories(body, 6))) == 6  # diverse, not one category

    def test_popular_experiences_lead_for_cold_start(self, client, make_user, catalogue, add_events):
        hit = catalogue["social"][3]
        for _ in range(3):
            add_events(make_user(), (hit, "like", 1))

        body = recs(client, make_user())

        assert body["items"][0]["experience"]["id"] == hit.id
        assert "popular with other L.I.V.E users" in body["items"][0]["reasons"]


class TestCandidatesAndFeedback:
    def test_completed_and_disliked_are_never_recommended(self, client, user, catalogue, add_events):
        done, hated = catalogue["outdoors"][0], catalogue["outdoors"][1]
        add_events(user, (done, "complete", 2), (hated, "dislike", 1))

        body = recs(client, user, limit=50)

        ids = {i["experience"]["id"] for i in body["items"]}
        assert done.id not in ids and hated.id not in ids
        assert body["candidate_count"] == len(CATEGORIES) * 4 - 2

    def test_skipped_category_sinks(self, client, user, catalogue, add_events):
        add_events(user, *[(e, "skip", 1) for e in catalogue["social"]], (catalogue["learning"][0], "save", 1))

        body = recs(client, user, limit=50)

        order = categories(body, n=50)
        assert order[0] == "learning"
        assert order.index("social") > len(order) // 2

    def test_saved_but_unfinished_item_is_recommended_with_reason(self, client, user, catalogue, add_events):
        saved = catalogue["creative"][2]
        add_events(user, (saved, "view", 2), (saved, "save", 2))

        top = recs(client, user)["items"][0]

        assert top["experience"]["id"] == saved.id
        assert "you saved this earlier" in top["reasons"]


class TestContract:
    def test_response_schema(self, client, user, catalogue, add_events):
        add_events(user, (catalogue["outdoors"][0], "like", 1))

        body = recs(client, user, limit=3)

        assert set(body) == {"user_id", "strategy", "generated_at", "candidate_count", "items"}
        assert body["user_id"] == user.id
        item = body["items"][0]
        assert set(item) == {"rank", "score", "relevance", "reasons", "features", "experience"}
        assert [i["rank"] for i in body["items"]] == [1, 2, 3]
        assert 0 <= item["score"] <= item["relevance"] <= 1
        assert set(item["features"]) == {
            "category_match", "interaction_preference", "difficulty_match", "duration_match",
            "cost_match", "popularity", "freshness", "novelty",
        }
        assert set(item["experience"]) >= {"id", "title", "category", "difficulty", "duration_minutes", "cost"}

    def test_scores_are_non_increasing(self, client, user, catalogue, add_events):
        add_events(user, (catalogue["creative"][0], "save", 3))
        scores = [i["score"] for i in recs(client, user, limit=50)["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_deterministic(self, client, user, catalogue, add_events):
        add_events(user, (catalogue["outdoors"][0], "save", 5), (catalogue["social"][0], "skip", 1))
        first = [i["experience"]["id"] for i in recs(client, user, limit=50)["items"]]
        second = [i["experience"]["id"] for i in recs(client, user, limit=50)["items"]]
        assert first == second

    def test_offset_pages_through_the_same_ranking(self, client, user, catalogue, add_events):
        add_events(user, (catalogue["outdoors"][0], "save", 1))
        full = [i["experience"]["id"] for i in recs(client, user, limit=20)["items"]]
        page = recs(client, user, limit=5, offset=5)
        assert [i["experience"]["id"] for i in page["items"]] == full[5:10]
        assert page["items"][0]["rank"] == 6

    def test_default_limit_is_10(self, client, user, catalogue):
        assert len(recs(client, user)["items"]) == 10

    def test_empty_catalogue(self, client, user):
        body = recs(client, user)
        assert body["items"] == [] and body["candidate_count"] == 0

    def test_nonexistent_user_returns_404(self, client, nonexistent_id):
        response = client.get(f"/users/{nonexistent_id}/recommendations")
        assert response.status_code == 404
        assert response.json()["detail"] == f"User {nonexistent_id} not found"

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"limit": "x"}, {"offset": -1}])
    def test_invalid_parameters_return_422(self, client, user, params):
        assert client.get(f"/users/{user.id}/recommendations", params=params).status_code == 422

    def test_reading_recommendations_writes_nothing(self, client, db_session, user, catalogue):
        before = db_session.scalar(select(func.count()).select_from(Interaction))
        recs(client, user)
        assert db_session.scalar(select(func.count()).select_from(Interaction)) == before
