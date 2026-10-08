"""Unit tests for the pure recommender pipeline (no database, fixed clock)."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.enums import EventType as E
from app.recommender.candidates import generate_candidates
from app.recommender.config import DEFAULT_CONFIG, NEUTRAL
from app.recommender.evaluation import (
    UserEvent,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    temporal_holdout,
)
from app.recommender.models import Event, ExperienceInfo
from app.recommender.profile import build_profile, recency_weight
from app.recommender.ranking import Scored, diversify, rank
from app.recommender.scoring import (
    compute_features,
    cost_match,
    difficulty_match,
    duration_match,
    popularity,
    weighted_score,
)
from app.recommender.service import count_fans, recommend

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def exp(id, category, difficulty="beginner", duration=60, cost=0, age_days=30, title=None):
    return ExperienceInfo(id, title or f"{category}-{id}", category, difficulty, duration, cost,
                          NOW - timedelta(days=age_days))


# 4 categories x 3 experiences, ids 1-12, otherwise identical so only behaviour differs.
CATALOGUE = [exp(i, cat) for i, cat in enumerate(
    ["outdoors"] * 3 + ["creative"] * 3 + ["wellness"] * 3 + ["social"] * 3, start=1)]
BY_ID = {e.id: e for e in CATALOGUE}


def ev(experience_id, event_type, days_ago=1.0):
    return Event(experience_id, event_type, NOW - timedelta(days=days_ago))


def profile_of(*events, catalogue=BY_ID, config=DEFAULT_CONFIG):
    return build_profile(list(events), catalogue, NOW, config)


def top_ids(events, catalogue=CATALOGUE, fans=None, **kw):
    result = recommend(catalogue, list(events), fans or {}, NOW, **kw)
    return [r.experience.id for r in result.items]


def top_categories(events, n=3, **kw):
    return [BY_ID[i].category for i in top_ids(events, **kw)[:n]]


# ---------- 1-3: history size ----------

class TestHistory:
    def test_empty_history_is_cold_start(self):
        assert profile_of().is_cold_start
        assert recommend(CATALOGUE, [], {}, NOW).strategy == "cold_start"

    def test_search_only_history_is_still_cold_start(self):
        # V2 cannot use query text yet (V3), so a search gives no personal signal.
        assert recommend(CATALOGUE, [Event(None, E.SEARCH, NOW)], {}, NOW).strategy == "cold_start"

    def test_one_interaction_personalises(self):
        profile = profile_of(ev(1, E.SAVE, days_ago=0))
        assert not profile.is_cold_start
        # One save (weight 4) is below the evidence scale (10): a partial, not full, preference.
        assert profile.category_affinity == {"outdoors": pytest.approx(0.4)}
        assert recommend(CATALOGUE, [ev(1, E.SAVE)], {}, NOW).strategy == "personalized"

    def test_strong_evidence_reaches_full_affinity(self):
        events = [ev(1, t, days_ago=0) for t in (E.VIEW, E.CLICK, E.SAVE, E.LIKE, E.COMPLETE)]
        assert profile_of(*events).category_affinity["outdoors"] == 1.0

    def test_multiple_interactions_accumulate(self):
        one = profile_of(ev(1, E.VIEW))
        many = profile_of(ev(1, E.VIEW), ev(1, E.CLICK), ev(1, E.SAVE))
        assert many.item_affinity[1] > one.item_affinity[1]
        assert many.signal_count == 3


# ---------- 4-9: feedback types ----------

class TestFeedback:
    def test_positive_feedback_raises_its_category(self):
        assert top_categories([ev(4, E.LIKE), ev(5, E.SAVE)], n=2) == ["creative", "creative"]

    def test_negative_feedback_pushes_category_below_neutral(self):
        profile = profile_of(ev(1, E.SKIP), ev(2, E.DISLIKE), ev(4, E.SAVE))
        assert profile.category_affinity["outdoors"] < 0
        features = compute_features(BY_ID[3], profile, {}, NOW)
        assert features["category_match"] < NEUTRAL
        assert "outdoors" not in top_categories([ev(1, E.SKIP), ev(2, E.DISLIKE), ev(4, E.SAVE)], n=4)

    def test_save_outweighs_view(self):
        profile = profile_of(ev(1, E.VIEW), ev(4, E.SAVE))
        assert profile.item_affinity[4] > profile.item_affinity[1]
        assert profile.category_affinity["creative"] > profile.category_affinity["outdoors"]

    def test_event_weight_order_is_as_configured(self):
        w = DEFAULT_CONFIG.event_weights
        assert w[E.COMPLETE] > w[E.LIKE] > w[E.SAVE] > w[E.CLICK] > w[E.VIEW] > 0
        assert w[E.DISLIKE] < w[E.SKIP] < 0
        assert w[E.SAVE] == -w[E.UNSAVE] and w[E.LIKE] == -w[E.UNLIKE]

    def test_unsave_cancels_save(self):
        profile = profile_of(ev(1, E.SAVE, 2), ev(1, E.UNSAVE, 1))
        assert 1 not in profile.saved
        assert profile.item_affinity[1] < profile_of(ev(1, E.SAVE, 2)).item_affinity[1]

    def test_unlike_removes_like(self):
        profile = profile_of(ev(1, E.LIKE, 2), ev(1, E.UNLIKE, 1))
        assert 1 not in profile.liked

    def test_completion_is_strongest_and_excludes_the_item(self):
        profile = profile_of(ev(1, E.COMPLETE), ev(4, E.LIKE))
        assert profile.item_affinity[1] > profile.item_affinity[4]
        assert 1 not in top_ids([ev(1, E.COMPLETE)])

    def test_dislike_excludes_but_skip_only_penalises(self):
        ids = top_ids([ev(1, E.DISLIKE), ev(2, E.SKIP), ev(4, E.SAVE)], limit=12)
        assert 1 not in ids
        assert 2 in ids and ids.index(2) > ids.index(4)

    def test_like_after_dislike_restores_the_item(self):
        assert 1 in top_ids([ev(1, E.DISLIKE, 3), ev(1, E.LIKE, 1)], limit=12)


class TestRecency:
    def test_recency_weight_halves_every_half_life(self):
        h = DEFAULT_CONFIG.recency_half_life_days
        assert recency_weight(NOW, NOW, h) == 1.0
        assert recency_weight(NOW - timedelta(days=h), NOW, h) == pytest.approx(0.5)
        assert recency_weight(NOW - timedelta(days=2 * h), NOW, h) == pytest.approx(0.25)
        assert recency_weight(NOW + timedelta(days=5), NOW, h) == 1.0  # future = now

    def test_recent_interest_beats_older_stronger_interest(self):
        # Two saves of outdoors 120 days ago vs one creative save yesterday.
        events = [ev(1, E.SAVE, 120), ev(2, E.SAVE, 120), ev(4, E.SAVE, 1)]
        profile = profile_of(*events)
        assert profile.category_affinity["creative"] > profile.category_affinity["outdoors"]
        assert top_categories(events, n=1) == ["creative"]


# ---------- 10-12: attribute preferences ----------

class TestAttributePreferences:
    def test_category_preference_ranks_that_category_first(self):
        for liked_id, category in [(1, "outdoors"), (4, "creative"), (7, "wellness")]:
            assert top_categories([ev(liked_id, E.LIKE)], n=1) == [category]

    def test_difficulty_preference(self):
        catalogue = {1: exp(1, "outdoors", "advanced"), 2: exp(2, "outdoors", "advanced"),
                     3: exp(3, "creative", "beginner"), 4: exp(4, "creative", "advanced")}
        profile = profile_of(ev(1, E.LIKE), ev(2, E.SAVE), catalogue=catalogue)
        assert profile.preferred_difficulty == pytest.approx(2.0)
        assert difficulty_match(catalogue[4], profile, DEFAULT_CONFIG) == 1.0
        assert difficulty_match(catalogue[3], profile, DEFAULT_CONFIG) == 0.0
        # Same category (no preference), differing only in difficulty: advanced wins.
        ids = top_ids([ev(1, E.LIKE), ev(2, E.SAVE)], catalogue=list(catalogue.values()))
        assert ids.index(4) < ids.index(3)

    def test_unknown_difficulty_is_neutral(self):
        profile = profile_of(ev(1, E.LIKE))
        assert difficulty_match(exp(99, "outdoors", "extreme"), profile, DEFAULT_CONFIG) == NEUTRAL

    def test_cost_preference(self):
        catalogue = {1: exp(1, "outdoors", cost=200), 2: exp(2, "outdoors", cost=300),
                     3: exp(3, "social", cost=100), 4: exp(4, "social", cost=3000)}
        profile = profile_of(ev(1, E.LIKE), ev(2, E.LIKE), catalogue=catalogue)
        assert profile.preferred_cost == pytest.approx(250)
        assert cost_match(catalogue[3], profile, DEFAULT_CONFIG) == 1.0     # cheaper than usual
        assert cost_match(catalogue[4], profile, DEFAULT_CONFIG) < 0.15     # far pricier
        ids = top_ids([ev(1, E.LIKE), ev(2, E.LIKE)], catalogue=list(catalogue.values()))
        assert ids.index(3) < ids.index(4)

    def test_duration_preference_uses_ratios(self):
        catalogue = {1: exp(1, "outdoors", duration=60)}
        profile = profile_of(ev(1, E.LIKE), catalogue=catalogue)
        assert profile.preferred_duration == pytest.approx(60)
        assert duration_match(exp(2, "x", duration=120), profile) == pytest.approx(0.5)
        assert duration_match(exp(3, "x", duration=30), profile) == pytest.approx(0.5)

    def test_no_positive_history_means_neutral_attributes(self):
        profile = profile_of(ev(1, E.SKIP))
        assert profile.preferred_cost is None and profile.preferred_difficulty is None
        assert cost_match(BY_ID[2], profile, DEFAULT_CONFIG) == NEUTRAL


# ---------- 13: cold start ----------

class TestColdStart:
    def test_uses_only_popularity_and_freshness(self):
        result = recommend(CATALOGUE, [], {}, NOW)
        assert all(set(r.features) == {"popularity", "freshness"} for r in result.items)
        assert all(r.reasons[0].startswith("a popular starting point") for r in result.items)

    def test_popular_items_first(self):
        assert top_ids([], fans={9: 5, 4: 3})[:2] == [9, 4]

    def test_fresh_items_first_when_nothing_is_popular(self):
        catalogue = [exp(1, "outdoors", age_days=200), exp(2, "creative", age_days=1)]
        assert top_ids([], catalogue=catalogue) == [2, 1]

    def test_cold_start_list_is_category_diverse(self):
        result = recommend(CATALOGUE, [], {i: 1 for i in range(1, 13)}, NOW, limit=4)
        assert len({r.experience.category for r in result.items}) == 4


# ---------- 14-16: diversity, candidates, determinism ----------

class TestDiversity:
    def scored(self):
        # Three outdoors items slightly ahead of everything else.
        rel = {1: 0.80, 2: 0.79, 3: 0.78, 4: 0.75, 7: 0.74, 10: 0.73}
        return rank([Scored(BY_ID[i], r, {}) for i, r in rel.items()])

    def test_no_decay_keeps_relevance_order(self):
        assert [r.experience.id for r in diversify(self.scored(), 1.0)] == [1, 2, 3, 4, 7, 10]

    def test_decay_interleaves_categories(self):
        ids = [r.experience.id for r in diversify(self.scored(), 0.9)]
        assert ids[:4] == [1, 4, 7, 10]  # one per category first
        assert ids[4:] == [2, 3]

    def test_strong_preference_can_still_repeat_a_category(self):
        rel = {1: 0.95, 2: 0.94, 4: 0.50}
        ids = [r.experience.id for r in diversify(rank([Scored(BY_ID[i], v, {}) for i, v in rel.items()]), 0.9)]
        assert ids == [1, 2, 4]

    def test_score_reflects_penalty_relevance_does_not(self):
        out = diversify(self.scored(), 0.9)
        second_outdoor = next(r for r in out if r.experience.id == 2)
        assert second_outdoor.relevance == 0.79
        assert second_outdoor.score == pytest.approx(0.79 * 0.9)

    def test_default_top3_mixes_categories_for_a_focused_user(self):
        cats = top_categories([ev(1, E.VIEW)], n=4)
        assert len(set(cats)) >= 3


class TestCandidates:
    def test_excludes_completed_and_disliked(self):
        profile = profile_of(ev(1, E.COMPLETE), ev(2, E.DISLIKE))
        candidates, excluded = generate_candidates(CATALOGUE, profile)
        assert {c.id for c in candidates} == set(range(3, 13))
        assert excluded == {1: "already completed", 2: "disliked"}

    def test_exclusions_can_be_switched_off(self):
        config = replace(DEFAULT_CONFIG, exclude_completed=False, exclude_disliked=False)
        profile = profile_of(ev(1, E.COMPLETE), ev(2, E.DISLIKE))
        assert len(generate_candidates(CATALOGUE, profile, config)[0]) == 12

    def test_result_reports_candidates_and_exclusions(self):
        result = recommend(CATALOGUE, [ev(1, E.COMPLETE)], {}, NOW)
        assert result.candidate_count == 11 and result.excluded == {1: "already completed"}


class TestDeterminism:
    def test_same_input_same_output(self):
        events = [ev(1, E.SAVE, 3), ev(4, E.VIEW, 2), ev(8, E.SKIP, 1)]
        assert recommend(CATALOGUE, events, {5: 2}, NOW) == recommend(CATALOGUE, events, {5: 2}, NOW)

    def test_ties_broken_by_id(self):
        scored = [Scored(BY_ID[i], 0.5, {}) for i in (9, 3, 6)]
        assert [s.experience.id for s in rank(scored)] == [3, 6, 9]

    def test_pagination_is_a_slice_of_the_full_ranking(self):
        events = [ev(1, E.SAVE)]
        full = top_ids(events, limit=12)
        assert top_ids(events, limit=4, offset=4) == full[4:8]
        result = recommend(CATALOGUE, events, {}, NOW, limit=2, offset=3)
        assert [r.rank for r in result.items] == [4, 5]


# ---------- 17: personalisation ----------

class TestPersonalisation:
    def test_different_users_get_different_recommendations(self):
        outdoor = top_ids([ev(1, E.LIKE), ev(2, E.SAVE)])
        creative = top_ids([ev(4, E.LIKE), ev(5, E.SAVE)])
        cold = top_ids([])
        assert outdoor[:3] != creative[:3] != cold[:3]
        assert BY_ID[outdoor[0]].category == "outdoors"
        assert BY_ID[creative[0]].category == "creative"


# ---------- scoring helpers ----------

class TestScoring:
    def test_all_features_in_unit_interval(self):
        profile = profile_of(ev(1, E.LIKE), ev(4, E.SKIP), ev(7, E.DISLIKE, 50))
        for e in CATALOGUE:
            for name, value in compute_features(e, profile, {1: 3, 2: 1}, NOW).items():
                assert 0.0 <= value <= 1.0, name

    def test_weighted_score_is_normalised_average(self):
        assert weighted_score({"a": 1.0, "b": 0.0}, {"a": 3, "b": 1}) == pytest.approx(0.75)

    def test_popularity_is_log_scaled_relative_to_max(self):
        fans = {1: 0, 2: 1, 3: 7}
        assert popularity(BY_ID[3], fans) == 1.0
        assert popularity(BY_ID[1], fans) == 0.0
        assert popularity(BY_ID[2], fans) == pytest.approx(0.3333, abs=1e-3)  # log2/log8
        assert popularity(BY_ID[2], {}) == 0.0

    def test_count_fans_counts_distinct_users(self):
        assert count_fans([(1, 10), (1, 10), (2, 10), (3, 11)]) == {10: 2, 11: 1}


class TestReasons:
    def test_personalised_reasons_come_from_features(self):
        result = recommend(CATALOGUE, [ev(1, E.LIKE), ev(2, E.SAVE)], {}, NOW, limit=1)
        reasons = result.items[0].reasons
        assert "matches your interest in outdoors" in reasons
        assert 1 <= len(reasons) <= DEFAULT_CONFIG.max_reasons

    def test_saved_item_says_so(self):
        result = recommend(CATALOGUE, [ev(2, E.SAVE)], {}, NOW, limit=12)
        item = next(r for r in result.items if r.experience.id == 2)
        assert "you saved this earlier" in item.reasons


# ---------- evaluation ----------

class TestMetrics:
    def test_precision_recall_ndcg(self):
        recommended, relevant = [5, 1, 9, 2], {1, 2}
        assert precision_at_k(recommended, relevant, 4) == 0.5
        assert recall_at_k(recommended, relevant, 2) == 0.5
        # hits at ranks 2 and 4: (1/log2(3) + 1/log2(5)) / (1 + 1/log2(3))
        assert ndcg_at_k(recommended, relevant, 4) == pytest.approx(0.6509, abs=1e-4)
        assert ndcg_at_k([1, 2], relevant, 2) == 1.0
        assert ndcg_at_k([7, 8], relevant, 2) == 0.0

    def test_temporal_holdout_hides_latest_positives_without_leakage(self):
        events = [UserEvent(1, e) for e in [
            ev(1, E.SAVE, 40), ev(2, E.LIKE, 30), ev(4, E.VIEW, 21), ev(4, E.SAVE, 20),
            ev(5, E.COMPLETE, 10), ev(7, E.SKIP, 5),
        ]]
        [case] = temporal_holdout(events, n_holdout=2, min_train_positives=2)
        assert case.held_out == {4, 5}
        assert case.cutoff == NOW - timedelta(days=21)  # first event on a held-out item (the view)
        assert all(e.occurred_at < case.cutoff for e in case.train_events)
        assert {e.experience_id for e in case.train_events} == {1, 2}

    def test_users_with_too_little_history_are_skipped(self):
        events = [UserEvent(1, ev(1, E.SAVE)), UserEvent(1, ev(2, E.SAVE))]
        assert temporal_holdout(events, n_holdout=2, min_train_positives=2) == []
