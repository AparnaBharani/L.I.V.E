"""Tests for the demo seed script. seed() runs inside the rolled-back test transaction."""

from collections import Counter
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import Experience, Interaction, User
from scripts.seed import CATALOGUE, PROFILES, check_target_database, seed

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
POSITIVE = {"save", "like", "complete"}


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def events_of(db, username):
    user = db.scalars(select(User).where(User.username == username)).one()
    return db.execute(
        select(Interaction.event_type, Experience.category, Interaction.occurred_at)
        .outerjoin(Experience, Experience.id == Interaction.experience_id)
        .where(Interaction.user_id == user.id)
        .order_by(Interaction.occurred_at, Interaction.id)
    ).all()


class TestSafety:
    @pytest.mark.parametrize("url", [
        "postgresql+psycopg://u:p@localhost/live_db_test",
        "postgresql+psycopg://u:p@localhost/anything_test",
    ])
    def test_refuses_test_databases(self, url):
        with pytest.raises(SystemExit):
            check_target_database(url)

    def test_accepts_development_database(self):
        assert check_target_database("postgresql+psycopg://u:p@localhost/live_db") == "live_db"


class TestSeed:
    def test_creates_catalogue_users_and_histories(self, db_session):
        created = seed(db_session, NOW)

        assert created["experiences"] == len(CATALOGUE) == count(db_session, Experience)
        assert created["users"] == len(PROFILES) == count(db_session, User)
        assert 100 <= created["interactions"] == count(db_session, Interaction) <= 400
        assert len({c[1] for c in CATALOGUE}) == 6

    def test_rerun_creates_nothing_new(self, db_session):
        seed(db_session, NOW)
        before = [count(db_session, m) for m in (User, Experience, Interaction)]

        created = seed(db_session, NOW)

        assert created == {"users": 0, "experiences": 0, "interactions": 0, "histories_rebuilt": 0}
        assert [count(db_session, m) for m in (User, Experience, Interaction)] == before

    def test_deterministic_histories(self, db_session):
        seed(db_session, NOW)
        first = events_of(db_session, "demo_outdoor_maya")

        seed(db_session, NOW, reset=True)

        assert events_of(db_session, "demo_outdoor_maya") == first

    def test_reset_leaves_non_demo_users_alone(self, db_session, make_user, experience):
        real = make_user("real_person")
        db_session.add(Interaction(user_id=real.id, experience_id=experience.id, event_type="like"))
        db_session.flush()

        seed(db_session, NOW, reset=True)

        assert db_session.scalar(select(func.count()).where(Interaction.user_id == real.id)) == 1
        assert db_session.get(Experience, experience.id) is not None

    def test_cold_start_users_have_no_events(self, db_session):
        seed(db_session, NOW)
        assert events_of(db_session, "demo_coldstart_ella") == []
        assert events_of(db_session, "demo_coldstart_omar") == []

    @pytest.mark.parametrize("username, category", [
        ("demo_outdoor_maya", "outdoors"),
        ("demo_creative_lena", "creative"),
        ("demo_social_zara", "social"),
        ("demo_wellness_anika", "wellness"),
        ("demo_learning_sofia", "learning"),
        ("demo_adventure_arjun", "adventure"),
    ])
    def test_profiles_have_coherent_behaviour(self, db_session, username, category):
        seed(db_session, NOW)
        events = events_of(db_session, username)

        positive = Counter(c for t, c, _ in events if t in POSITIVE)
        assert positive.most_common(1)[0][0] == category
        # Avoided categories only ever get negative feedback.
        assert {t for t, *_ in events} & {"skip", "dislike"}

    def test_events_have_temporal_structure(self, db_session):
        seed(db_session, NOW)
        times = [at for *_, at in events_of(db_session, "demo_outdoor_maya")]

        assert times == sorted(times)
        assert (max(times) - min(times)).days >= 30  # spread over weeks, not one instant
        assert max(times) < NOW
