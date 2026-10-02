"""Unit tests for request/response schemas. No database needed."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.enums import EventType
from app.schemas import (
    ExperienceCreate,
    ExperienceResponse,
    InteractionCreate,
    InteractionResponse,
    UserCreate,
    UserResponse,
)

NON_SEARCH_EVENTS = [e for e in EventType if e is not EventType.SEARCH]


def error_types(exc: ValidationError) -> set[str]:
    return {err["type"] for err in exc.errors()}


# ---------- Experience ----------

VALID_EXPERIENCE = {
    "title": "Sunrise hike",
    "description": "A gentle 5 km walk to the hilltop.",
    "category": "outdoors",
    "difficulty": "beginner",
    "duration_minutes": 120,
}


class TestExperienceCreate:
    def test_valid_experience_and_cost_defaults_to_zero(self):
        exp = ExperienceCreate.model_validate(VALID_EXPERIENCE)
        assert exp.cost == 0

    def test_whitespace_is_stripped(self):
        exp = ExperienceCreate.model_validate({**VALID_EXPERIENCE, "title": "  Sunrise hike  "})
        assert exp.title == "Sunrise hike"

    @pytest.mark.parametrize("field", ["title", "description", "category", "difficulty"])
    def test_blank_text_fields_rejected(self, field):
        with pytest.raises(ValidationError) as exc:
            ExperienceCreate.model_validate({**VALID_EXPERIENCE, field: "   "})
        assert error_types(exc.value) == {"string_too_short"}

    def test_title_too_long_rejected(self):
        with pytest.raises(ValidationError):
            ExperienceCreate.model_validate({**VALID_EXPERIENCE, "title": "x" * 201})

    @pytest.mark.parametrize("duration", [0, -5])
    def test_non_positive_duration_rejected(self, duration):
        with pytest.raises(ValidationError):
            ExperienceCreate.model_validate({**VALID_EXPERIENCE, "duration_minutes": duration})

    def test_negative_cost_rejected(self):
        with pytest.raises(ValidationError):
            ExperienceCreate.model_validate({**VALID_EXPERIENCE, "cost": -100})

    @pytest.mark.parametrize("value", ["120", 120.0, True])
    def test_numbers_must_be_real_integers(self, value):
        # strict=True: no silent string/float/bool -> int conversion
        with pytest.raises(ValidationError):
            ExperienceCreate.model_validate({**VALID_EXPERIENCE, "duration_minutes": value})

    @pytest.mark.parametrize("field", ["id", "created_at"])
    def test_server_controlled_fields_rejected(self, field):
        with pytest.raises(ValidationError) as exc:
            ExperienceCreate.model_validate({**VALID_EXPERIENCE, field: 999})
        assert error_types(exc.value) == {"extra_forbidden"}

    def test_missing_required_field_rejected(self):
        data = {k: v for k, v in VALID_EXPERIENCE.items() if k != "title"}
        with pytest.raises(ValidationError) as exc:
            ExperienceCreate.model_validate(data)
        assert error_types(exc.value) == {"missing"}


# ---------- User ----------

class TestUserCreate:
    @pytest.mark.parametrize("username", ["abc", "aparna_b", "User_42", "x" * 50])
    def test_valid_usernames(self, username):
        assert UserCreate.model_validate({"username": username}).username == username

    @pytest.mark.parametrize(
        "username",
        ["ab", "x" * 51, "has space", "dash-name", "émoji", "a@b", ""],
    )
    def test_invalid_usernames_rejected(self, username):
        with pytest.raises(ValidationError):
            UserCreate.model_validate({"username": username})

    def test_client_cannot_set_id(self):
        with pytest.raises(ValidationError):
            UserCreate.model_validate({"username": "aparna", "id": 1})


# ---------- Interaction ----------

class TestInteractionEventType:
    def test_every_defined_event_type_is_accepted(self):
        # One valid payload per type, built from the enum so new types are covered.
        for event in EventType:
            payload = (
                {"event_type": event, "query_text": "weekend ideas"}
                if event is EventType.SEARCH
                else {"event_type": event, "experience_id": 1}
            )
            assert InteractionCreate.model_validate(payload).event_type is event

    def test_accepts_plain_string_and_converts_to_enum(self):
        event = InteractionCreate.model_validate({"event_type": "save", "experience_id": 1})
        assert event.event_type is EventType.SAVE

    @pytest.mark.parametrize("bad", ["purchase", "start", "abandon", "SAVE", "", None])
    def test_unknown_event_types_rejected(self, bad):
        with pytest.raises(ValidationError) as exc:
            InteractionCreate.model_validate({"event_type": bad, "experience_id": 1})
        assert "event_type" in {err["loc"][0] for err in exc.value.errors()}


class TestSearchEventShape:
    def test_valid_search(self):
        event = InteractionCreate.model_validate(
            {"event_type": "search", "query_text": "  relaxing weekend  "}
        )
        assert event.query_text == "relaxing weekend"
        assert event.experience_id is None

    def test_search_requires_query_text(self):
        with pytest.raises(ValidationError, match="search events require query_text"):
            InteractionCreate.model_validate({"event_type": "search"})

    def test_search_rejects_blank_query_text(self):
        with pytest.raises(ValidationError) as exc:
            InteractionCreate.model_validate({"event_type": "search", "query_text": "   "})
        assert error_types(exc.value) == {"string_too_short"}

    def test_search_rejects_too_long_query_text(self):
        with pytest.raises(ValidationError):
            InteractionCreate.model_validate({"event_type": "search", "query_text": "q" * 501})

    def test_search_rejects_experience_id(self):
        with pytest.raises(ValidationError, match="must not include experience_id"):
            InteractionCreate.model_validate(
                {"event_type": "search", "query_text": "hikes", "experience_id": 1}
            )


class TestNonSearchEventShape:
    @pytest.mark.parametrize("event", NON_SEARCH_EVENTS)
    def test_valid(self, event):
        result = InteractionCreate.model_validate({"event_type": event, "experience_id": 7})
        assert result.experience_id == 7 and result.query_text is None

    @pytest.mark.parametrize("event", NON_SEARCH_EVENTS)
    def test_requires_experience_id(self, event):
        with pytest.raises(ValidationError, match=f"{event.value} events require experience_id"):
            InteractionCreate.model_validate({"event_type": event})

    @pytest.mark.parametrize("event", NON_SEARCH_EVENTS)
    def test_rejects_query_text(self, event):
        with pytest.raises(ValidationError, match="query_text is only allowed for search events"):
            InteractionCreate.model_validate(
                {"event_type": event, "experience_id": 7, "query_text": "hikes"}
            )

    @pytest.mark.parametrize("bad_id", [0, -1, "7", 7.0])
    def test_experience_id_must_be_positive_integer(self, bad_id):
        with pytest.raises(ValidationError):
            InteractionCreate.model_validate({"event_type": "view", "experience_id": bad_id})


class TestInteractionServerControlledFields:
    @pytest.mark.parametrize(
        "field, value",
        [("id", 1), ("user_id", 1), ("occurred_at", "2026-01-01T00:00:00Z")],
    )
    def test_rejected(self, field, value):
        with pytest.raises(ValidationError) as exc:
            InteractionCreate.model_validate({"event_type": "view", "experience_id": 1, field: value})
        assert error_types(exc.value) == {"extra_forbidden"}


class TestInteractionProperties:
    def base(self, properties):
        return {"event_type": "view", "experience_id": 1, "properties": properties}

    def test_flat_scalar_properties_accepted(self):
        props = {"source": "home_feed", "position": 3, "score": 0.82, "from_search": False}
        assert InteractionCreate.model_validate(self.base(props)).properties == props

    def test_properties_optional(self):
        assert InteractionCreate.model_validate(self.base(None)).properties is None

    @pytest.mark.parametrize(
        "props",
        [
            {"nested": {"a": 1}},       # no nested objects
            {"tags": ["a", "b"]},       # no lists
            {"missing": None},          # no nulls
            {"": "empty key"},
            {"k" * 51: "key too long"},
            {"v": "x" * 201},           # value too long
            {f"k{i}": i for i in range(21)},  # too many keys
        ],
    )
    def test_invalid_properties_rejected(self, props):
        with pytest.raises(ValidationError):
            InteractionCreate.model_validate(self.base(props))


# ---------- Responses ----------

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


class TestResponses:
    """Response schemas read ORM-like objects (from_attributes) and enforce no input rules."""

    def test_experience_response_from_attributes(self):
        row = SimpleNamespace(**VALID_EXPERIENCE, id=1, cost=0, created_at=NOW)
        assert ExperienceResponse.model_validate(row).model_dump()["created_at"] == NOW

    def test_response_does_not_reapply_request_rules(self):
        # A row stored before a rule was tightened must still be readable.
        row = SimpleNamespace(**{**VALID_EXPERIENCE, "title": "x" * 500}, id=1, cost=0, created_at=NOW)
        assert len(ExperienceResponse.model_validate(row).title) == 500

    def test_user_response(self):
        row = SimpleNamespace(id=1, username="aparna", created_at=NOW)
        assert UserResponse.model_validate(row).username == "aparna"

    def test_interaction_response_serialises_enum_as_string(self):
        row = SimpleNamespace(
            id=10, user_id=1, experience_id=7, event_type="save",
            query_text=None, properties={"source": "home_feed"}, occurred_at=NOW,
        )
        data = InteractionResponse.model_validate(row).model_dump(mode="json")
        assert data["event_type"] == "save"
        assert data["occurred_at"] == "2026-10-02T12:00:00Z"
