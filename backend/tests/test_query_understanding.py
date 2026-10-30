"""Tests for natural-language query understanding (pure, no database)."""

import json
from pathlib import Path

import pytest

from app.search.query import CHEAP_MAX_COST, parse_query

LABELS = json.loads((Path(__file__).parent / "data" / "query_labels.json").read_text(encoding="utf-8"))
FIELDS = ("max_cost", "max_duration_minutes", "difficulty")


def matches(label: dict) -> bool:
    parsed = parse_query(label["q"])
    return set(parsed.categories) == set(label.get("categories", [])) and all(
        getattr(parsed, f) == label.get(f) for f in FIELDS
    )


@pytest.mark.parametrize("label", LABELS["dev"], ids=lambda l: l["q"])
def test_dev_queries(label):
    assert matches(label), parse_query(label["q"])


def test_holdout_accuracy_does_not_regress():
    # A floor, not a target: the holdout set is never tuned against.
    accuracy = sum(matches(label) for label in LABELS["holdout"]) / len(LABELS["holdout"])
    assert accuracy >= 0.75


class TestConstraints:
    @pytest.mark.parametrize("text, cost", [
        ("under ₹1000", 1000), ("below rs. 750", 750), ("less than 300 rupees", 300),
        ("₹1,500 budget", 1500), ("under 2k", 2000), ("no more than 1200", 1200),
    ])
    def test_budget(self, text, cost):
        assert parse_query(f"trek {text}").max_cost == cost

    @pytest.mark.parametrize("text, minutes", [
        ("30 min", 30), ("under 2 hours", 120), ("1.5 hrs", 90), ("an hour", 60),
        ("half an hour", 30), ("half a day", 300), ("all day", 720), ("two days", 2880),
    ])
    def test_duration(self, text, minutes):
        assert parse_query(f"hike {text}").max_duration_minutes == minutes

    def test_hours_are_never_read_as_money(self):
        parsed = parse_query("under 2 hours")
        assert parsed.max_cost is None and parsed.max_duration_minutes == 120

    def test_a_count_of_people_is_not_a_budget(self):
        assert parse_query("activity for 4 friends").max_cost is None

    def test_free_time_is_not_free_of_charge(self):
        assert parse_query("my free time").max_cost is None
        assert parse_query("free pottery").max_cost == 0

    def test_a_minimum_is_ignored_rather_than_treated_as_a_maximum(self):
        assert parse_query("at least 3 hours").max_duration_minutes is None

    def test_vague_price_words_use_the_documented_assumption(self):
        assert parse_query("affordable dance class").max_cost == CHEAP_MAX_COST


class TestText:
    def test_constraints_and_filler_leave_the_search_terms(self):
        assert parse_query("I want a pottery class under ₹1000 this weekend").text == "pottery class"

    def test_category_words_stay_searchable(self):
        assert "yoga" in parse_query("free yoga").text

    def test_only_constraints_leaves_no_text(self):
        parsed = parse_query("free")
        assert parsed.text == "" and parsed.has_filters

    def test_the_phrases_that_set_constraints_are_reported(self):
        assert set(parse_query("hike under ₹500 for 2 hours").matched) == {"2 hours", "under ₹500"}

    @pytest.mark.parametrize("q", ["", "   ", "!!!", "₹", "under", "1000", "' OR 1=1 --"])
    def test_odd_input_never_crashes_or_invents_filters(self, q):
        parsed = parse_query(q)
        assert parsed.max_duration_minutes is None and parsed.difficulty is None
