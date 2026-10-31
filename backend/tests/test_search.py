"""Retrieval, fusion and the /search API. Uses a tiny fake embedder, so no model is needed."""

import numpy as np
import pytest

from app.main import app
from app.search.embedding import embed_missing, get_embedder
from app.search.retrieval import Fused, reciprocal_rank_fusion

# Each word maps to a meaning axis, so "ceramics" and "pottery" are close without sharing text.
AXES = {"pottery": 0, "ceramics": 0, "clay": 0, "hike": 1, "trek": 1, "yoga": 2, "stretching": 2}


class FakeEmbedder:
    name = "fake-embedder"

    def _vector(self, text: str) -> list[float]:
        vector = np.full(4, 0.01)
        for word in text.lower().replace(".", " ").split():
            if word in AXES:
                vector[AXES[word]] += 1.0
        return vector.tolist()

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture
def catalogue(make_experience, db_session):
    items = {
        "wheel": make_experience(title="Wheel class", description="Shape clay on a wheel.", category="creative",
                                 difficulty="beginner", cost=800, duration_minutes=120),
        "mugs": make_experience(title="Pottery mugs", description="Make a set of mugs.", category="creative",
                                difficulty="advanced", cost=2200, duration_minutes=480),
        "ridge": make_experience(title="Ridge hike", description="A morning walk.", category="outdoors",
                                 difficulty="beginner", cost=0, duration_minutes=150),
        "flow": make_experience(title="Morning yoga", description="Stretching in the park.", category="wellness",
                                difficulty="beginner", cost=0, duration_minutes=60),
    }
    return items


@pytest.fixture
def semantic(client, db_session, catalogue):
    embedder = FakeEmbedder()
    embed_missing(db_session, embedder)
    app.dependency_overrides[get_embedder] = lambda: embedder
    return embedder


def search(client, **params):
    response = client.get("/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(body):
    return [i["experience"]["id"] for i in body["items"]]


class TestFusion:
    def test_uses_positions_not_scores(self):
        assert reciprocal_rank_fusion({"a": [1, 2]}) == [
            Fused(1, 1 / 61, {"a": 1}), Fused(2, 1 / 62, {"a": 2}),
        ]

    def test_agreement_between_retrievers_wins(self):
        fused = reciprocal_rank_fusion({"keyword": [1, 2, 3], "semantic": [9, 2, 8]})
        assert fused[0].experience_id == 2
        assert fused[0].ranks == {"keyword": 2, "semantic": 2}

    def test_ties_are_deterministic(self):
        assert [f.experience_id for f in reciprocal_rank_fusion({"a": [5], "b": [3]})] == [3, 5]

    def test_nothing_to_fuse(self):
        assert reciprocal_rank_fusion({"a": [], "b": []}) == []


class TestKeyword:
    def test_finds_words_and_stems(self, client, catalogue):
        body = search(client, q="hiking")
        assert ids(body) == [catalogue["ridge"].id]
        assert body["mode"] == "keyword"
        assert body["items"][0]["keyword_rank"] == 1 and body["items"][0]["semantic_rank"] is None

    def test_a_sentence_matches_on_any_word(self, client, catalogue):
        assert catalogue["ridge"].id in ids(search(client, q="looking for a hike with a nice view"))

    def test_title_outranks_description(self, client, make_experience):
        in_description = make_experience(title="Evening", description="Includes some juggling.")
        in_title = make_experience(title="Juggling basics", description="Evening class.")
        assert ids(search(client, q="juggling")) == [in_title.id, in_description.id]

    def test_no_match(self, client, catalogue):
        body = search(client, q="xylophone")
        assert body["items"] == [] and body["total"] == 0


class TestSemantic:
    def test_finds_related_meaning_without_shared_words(self, client, semantic, catalogue):
        body = search(client, q="ceramics")
        assert body["mode"] == "hybrid"
        assert set(ids(body)) == {catalogue["wheel"].id, catalogue["mugs"].id}
        assert all(i["keyword_rank"] is None and i["semantic_rank"] for i in body["items"])

    def test_unrelated_text_stays_below_the_threshold(self, client, semantic, catalogue):
        assert search(client, q="xylophone")["items"] == []

    def test_a_match_in_both_retrievers_ranks_first(self, client, semantic, catalogue):
        body = search(client, q="pottery")
        assert ids(body)[0] == catalogue["mugs"].id
        assert body["items"][0]["keyword_rank"] and body["items"][0]["semantic_rank"]

    def test_experiences_not_yet_embedded_stay_findable_by_keyword(self, client, semantic, make_experience):
        new = make_experience(title="Trek planning", description="Maps and packing.")
        assert new.id in ids(search(client, q="planning"))

    def test_vectors_from_another_model_are_ignored(self, client, semantic, db_session, catalogue):
        catalogue["wheel"].embedding_model = "old-model"
        db_session.flush()
        assert catalogue["wheel"].id not in ids(search(client, q="ceramics"))

    def test_embed_missing_is_idempotent(self, db_session, semantic):
        assert embed_missing(db_session, semantic) == 0


class TestFilters:
    def test_constraints_in_the_query_are_hard_filters(self, client, semantic, catalogue):
        body = search(client, q="pottery under ₹1000")
        assert ids(body) == [catalogue["wheel"].id]
        assert body["understood"]["max_cost"] == 1000
        assert body["understood"]["text"] == "pottery"

    def test_filters_apply_to_both_retrievers(self, client, semantic, catalogue):
        assert search(client, q="ceramics for beginners")["items"][0]["experience"]["id"] == catalogue["wheel"].id
        assert ids(search(client, q="ceramics for beginners")) == [catalogue["wheel"].id]

    def test_explicit_parameters_override_the_query(self, client, catalogue):
        body = search(client, q="pottery under ₹1000", max_cost=5000)
        assert body["understood"]["max_cost"] == 5000
        assert catalogue["mugs"].id in ids(body)

    def test_explicit_category_is_a_hard_filter(self, client, catalogue):
        assert ids(search(client, category="outdoors")) == [catalogue["ridge"].id]

    def test_query_category_is_only_a_hint(self, client, semantic, catalogue):
        body = search(client, q="relaxing yoga")
        assert body["understood"]["categories"] == ["wellness"]
        assert body["understood"]["category"] is None
        assert body["items"][0]["category_hint"] is True

    def test_only_constraints_browses_what_satisfies_them(self, client, catalogue):
        body = search(client, q="free")
        assert body["mode"] == "browse"
        assert set(ids(body)) == {catalogue["ridge"].id, catalogue["flow"].id}

    def test_empty_query_lists_everything(self, client, catalogue):
        assert search(client)["total"] == 4


class TestContract:
    def test_pagination(self, client, make_experience):
        made = [make_experience(title=f"Juggling {i}").id for i in range(5)]
        everything = search(client, q="juggling", limit=100)
        page = search(client, q="juggling", limit=2, offset=1)
        assert everything["total"] == page["total"] == 5
        assert set(ids(everything)) == set(made)
        assert ids(page) == ids(everything)[1:3]

    def test_deterministic(self, client, semantic, catalogue):
        assert ids(search(client, q="pottery clay")) == ids(search(client, q="pottery clay"))

    @pytest.mark.parametrize("params", [
        {"limit": 0}, {"limit": 101}, {"offset": -1}, {"max_cost": -1},
        {"max_duration_minutes": 0}, {"max_cost": 10**30}, {"q": "x" * 301},
    ])
    def test_invalid_parameters_return_422(self, client, params):
        assert client.get("/search", params=params).status_code == 422

    @pytest.mark.parametrize("q", ["' OR 1=1 --", "a & b | c", "!!!", "pottery:*", "\\", "(", "a\u0000b"])
    def test_query_syntax_is_treated_as_text(self, client, catalogue, q):
        assert client.get("/search", params={"q": q}).status_code == 200

    def test_works_without_the_model(self, client, catalogue):
        assert search(client, q="pottery")["mode"] == "keyword"

    def test_search_writes_nothing(self, client, catalogue, db_session):
        from sqlalchemy import func, select

        from app.models import Interaction
        search(client, q="pottery")
        assert db_session.scalar(select(func.count()).select_from(Interaction)) == 0
