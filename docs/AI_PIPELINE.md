# AI pipeline

How L.I.V.E searches, ranks and explains, and how each part was measured. The [README](../README.md) has the short version.

All figures here come from synthetic data and developer-written labels. They compare methods with each other and do not show real-world quality.

## Recommendation engine

### The problem

`GET /users/{user_id}/recommendations` answers *"given what this user has done, which experiences
are most relevant now?"* It uses only structured data (experience attributes plus the
interaction log). It uses no ML, embeddings, LLMs or external services, and every score can be
explained.

### Architecture

```
 GET /users/{id}/recommendations        routers/recommendations.py   HTTP only (404, 422, response shape)
            │
 recommender/service.py                 recommend_for_user(): load experiences, the user's events and
            │                           fan counts from PostgreSQL, then call the pure pipeline:
            │
            │  recommend(experiences, user_events, fans, now, config)
            ├── profile.py      events ──► UserProfile (recency-weighted category/item affinity,
            │                              preferred difficulty/duration/cost, saved/liked/disliked/completed)
            ├── candidates.py   catalogue − completed − disliked ──► candidate pool
            ├── scoring.py      8 features per candidate, each in [0, 1] ──► weighted score
            ├── ranking.py      sort (score, id) ──► greedy category-diversity re-rank ──► page (limit/offset)
            └── explain.py      feature values ──► templated reasons
 recommender/config.py                  every weight and constant (RecommenderConfig)
 recommender/evaluation.py              temporal hold-out + Precision/Recall/NDCG@K + baselines
```

Only `service.py` touches the database. Every other stage is a pure function of plain dataclasses,
which is why they can be unit-tested with a fixed clock and why the offline evaluation runs the
*same* code as the API. Retrieval (candidates) is separate from ranking (scoring), so new sources can add
keyword/vector candidate sources without touching scoring.

### 1. User profile (`profile.py`)

Each event type still in effect for an experience (see `state.py`) contributes a **signal** =
`event_weight × recency_weight`, using its latest time.

| Event | Weight | | Event | Weight |
|---|---|---|---|---|
| view | +1 | | unsave | none: removes the save |
| click | +2 | | unlike | none: removes the like |
| save | +4 | | skip | −3 |
| like | +5 | | dislike | −5 |
| complete | +6 | | search | none: not about one experience |

**Recency:** `recency_weight = 0.5 ** (age_days / 30)`. An event loses half its influence every
30 days (1.0 today, 0.5 after a month, 0.25 after two). Future timestamps count as "now".

From the signals:
- **Category affinity** ∈ [−1, 1] = category sum / max(strongest category sum, **10**). Dividing by
  the strongest category makes long and short histories comparable. The evidence floor of 10
  (about view + click + save + like) stops one view from looking like certainty. A test caught this
  bug: one view used to give a category full weight.
- **Item affinity** = raw signal sum per experience.
- **Preferred difficulty / duration / cost**: averages over the experiences with *positive* item
  affinity, weighted by that affinity (duration uses a geometric mean, because durations compare
  as ratios). If the user has no positive history, these stay `None` (unknown).
- **State** replayed from the log (latest event wins): saved, liked, disliked, completed, seen.

A user with no experience-linked events is **cold start**.

### 2. Candidate generation (`candidates.py`)

All experiences, minus those the user **completed** and those they **currently dislike** (a later
`like` lifts a dislike). Both exclusions are configurable. Skipped items stay in, but are penalised
through their features. The response reports `candidate_count`.

### 3. Features (`scoring.py`)

Every feature is in [0, 1], so no feature dominates because its raw numbers are bigger. For
preference features, 0.5 means "no information".

| Feature | Weight | Definition |
|---|---|---|
| `category_match` | 0.40 | (category affinity + 1) / 2; unseen category = 0.5 |
| `interaction_preference` | 0.15 | (tanh(item affinity / 5) + 1) / 2; e.g. saved-but-not-done is high, skipped is low |
| `difficulty_match` | 0.10 | 1 − \|level − preferred level\| / 2 on beginner=0, intermediate=1, advanced=2 |
| `duration_match` | 0.10 | min(d, preferred) / max(d, preferred): 120 vs 60 min → 0.5 |
| `cost_match` | 0.10 | 1 if cost ≤ preferred, else (preferred + 100) / (cost + 100) |
| `popularity` | 0.05 | log(1 + fans) / log(1 + max fans); fans = users who currently have a save, like or completion in effect |
| `freshness` | 0.05 | 0.5 ** (days since created / 60) |
| `novelty` | 0.05 | 1 if the user never interacted with it, else 0 |
| `semantic_match` | 0.15 | cosine similarity to the user's taste vector, stretched to [0, 1] |

The **taste vector** is the average embedding of experiences with positive affinity, weighted by
that affinity. It gives similarity beyond category: pottery can lead to block printing. Weights are
normalised by their sum, and a feature set to 0 is switched off. Without embeddings the feature is
neutral, so recommendations still work.

### 4. Scoring and ranking

`relevance = Σ wᵢ·fᵢ / Σ wᵢ` ∈ [0, 1]. Candidates are sorted by relevance, with **ties broken by
experience id**, so the output is deterministic.

**Diversity** (`ranking.py`): a greedy re-rank picks, at each position, the candidate that maximises
`relevance × 0.9 ^ (items already picked from its category)`. A second item from a category must be
about 11% more relevant than the best item from an unused category to take the slot, and a third
about 23% more. A strong preference can still fill several slots; a weak one can't. `score` in the
response is this adjusted value (it sets the order); `relevance` is the value before adjustment.
`offset` pages through the same diversified list.

### 5. Cold start

Users with no behaviour get `strategy: "cold_start"`. They are ranked by **popularity (0.6) and
freshness (0.4) only**, with the same diversity re-rank (so the list covers several categories).
The response, the reasons ("a popular starting point while we learn what you like") and the UI
("Popular picks to get you started") all say this is **not** personalised. One positive
interaction switches the user to `personalized`.

### 6. Reasons (`explain.py`)

Each reason is a fixed template, offered only when its feature is clearly strong (e.g.
`category_match ≥ 0.75` → "matches your interest in outdoors", saved → "you saved this earlier",
an unseen category → "something new for you: wellness"). Reasons are ordered by their feature's
contribution `wᵢ·fᵢ`, with at most 3. No LLM is involved, and the response also exposes the raw
`features`.

### 7. API

`GET /users/{user_id}/recommendations?limit=10&offset=0` (`limit` 1–50, `offset` ≥ 0). 404 for an
unknown user. Read-only: generating recommendations writes nothing.

Real response for the seeded user `demo_outdoor_maya` (`?limit=1`, experience fields shortened):

```json
{
  "user_id": 10, "strategy": "personalized", "generated_at": "2026-10-07T18:40:38.074775Z", "candidate_count": 41,
  "items": [{
    "rank": 1, "score": 0.8581, "relevance": 0.8581,
    "reasons": ["matches your interest in outdoors", "you saved this earlier", "free"],
    "features": {"category_match": 1.0, "interaction_preference": 0.94, "difficulty_match": 0.7543,
                 "duration_match": 0.6586, "cost_match": 1.0, "popularity": 0.7925, "freshness": 0.7234, "novelty": 0.0},
    "experience": {"id": 15, "title": "Coastal cleanup and beach walk", "category": "outdoors",
                   "difficulty": "beginner", "duration_minutes": 180, "cost": 0, "...": "..."}
  }]
}
```

### 8. Evaluation (`python -m scripts.evaluate`)

**Protocol: temporal leave-last-out.** A *positive* experience is one the user saved, liked or
completed. For each user with at least 4 positives, the **2 most recent positive experiences are
held out**. The cutoff is the first event of any kind on a held-out item. The profile **and**
popularity are rebuilt from events before the cutoff only, so no future data leaks in. Then we ask:
*would the top K, generated at the cutoff, have contained what the user went on to engage with?*

- **Precision@K**: share of the K recommendations that were held-out positives.
- **Recall@K**: share of the held-out positives found in the top K.
- **NDCG@K**: like recall, but a hit at rank 1 counts more than a hit at rank K (1/log₂(rank+1)), normalised to [0, 1].
- **Coverage@K**: share of the catalogue appearing in anyone's top K. **Categories@K**: distinct categories per list.

Results on the seeded data (42 experiences, 343 events, 11 evaluable users):

| K=5 | Precision | Recall | NDCG | Coverage | Categories |
|---|---|---|---|---|---|
| random (mean of 20 seeds) | 0.056 | 0.141 | 0.106 | 0.761 | 3.74 |
| popularity | 0.036 | 0.091 | 0.046 | 0.262 | 3.09 |
| rules only (baseline) | 0.164 | 0.409 | 0.378 | 0.524 | 3.82 |
| **current** (with `semantic_match`) | **0.200** | **0.500** | **0.409** | 0.595 | **3.27** |
| current without diversity | 0.273 | 0.682 | 0.524 | 0.833 | 1.64 |

| K=10 | Precision | Recall | NDCG | Coverage | Categories |
|---|---|---|---|---|---|
| random | 0.052 | 0.259 | 0.152 | 0.958 | 5.20 |
| popularity | 0.018 | 0.091 | 0.046 | 0.452 | 5.00 |
| rules only (baseline) | 0.109 | 0.545 | 0.437 | 0.762 | 5.64 |
| **current** | **0.118** | **0.591** | **0.444** | 0.786 | **5.73** |
| current without diversity | 0.145 | 0.727 | 0.544 | 0.929 | 3.55 |

What the numbers say:
- The recommender finds held-out positives about **3.5× more often than random at K=5**, and
  popularity is worse than random. Generic popular items aren't what a specific person does next.
- **`semantic_match` was adopted under a rule set before running the experiment**: beat the baseline
  by more than one held-out item on Recall@5 or NDCG@5 without lowering the other. Weight 0.15 passed
  (+2 of 22 items); 0.30 failed because NDCG fell. It costs some variety (3.82 to 3.27 categories).
- Making reversals and repeats correct moved the baseline's Recall@5 from 0.455 to 0.409, one
  held-out item, which is noise at this size. The weights were deliberately not re-tuned to recover it.
- **Diversity costs accuracy.** Turning it off raises Recall@5 from 0.50 to 0.68 but collapses lists
  to about 1.6 categories. The default is a deliberate middle point, and the sweep that chose it
  ran on this same data, so these figures are optimistic.
- `tests/test_evaluation.py` re-runs this on freshly seeded test data and fails if the recommender stops beating
  both baselines.

**Limitations:** the data is **synthetic**. The seed script generates behaviour from category
preferences, which is exactly what the recommender models, so good scores are partly built in. There are only
11 evaluable users and 2 held-out items each, so one user changes recall by about 0.05. Offline
hit-rate is not user value. Real validation needs real users, online signals (completion after
recommendation) and more held-out data.

### 9. Frontend flow

The catalogue page (`/`) shows **For You** above the full catalogue (`components/ForYou.tsx`):
6 recommendations with rank, score and reasons. Interacting with a recommended card posts a
normal event with `properties = {source: "recommendations", position, strategy}`. That changes the
user's newest event id, which triggers a re-fetch, so the loop is visible immediately:

```
recommendation ─► user action ─► POST /users/{id}/interactions ─► event log
      ▲                                                               │
      └──── GET /users/{id}/recommendations ◄── profile rebuilt ◄─────┘
```

### 10. Testing the recommender

| File | Tests |
|---|---|
| `test_recommender.py` | pure pipeline with a fixed clock: history size, every feedback type, unsave/unlike, recency, category/difficulty/cost/duration preferences, cold start, diversity, candidate exclusion, determinism, pagination, features in [0, 1], reasons, metric maths, hold-out without leakage |
| `test_api_recommendations.py` | API on the test database: outdoor/creative/wellness users get their category first, different users get different lists, the event → recommendation loop, cold start, exclusions, skipped categories sink, response schema, determinism, pagination, 404, 422, read-only |
| `test_evaluation.py` | the recommender beats random and popularity on seeded test data; top 5 keeps ≥ 3 categories |

### 11. Limitations

- **Hand-set weights**, tuned lightly on synthetic data. Learning them needs real interaction data.
- **No collaborative signal** beyond global popularity ("people like you also did…").
- **Popularity counts all time equally**, with no decay for old fans.
- **Full scan:** every request scores the whole catalogue (fine for 42 items, not for 100k).
- **No context** (time of day, location, weather) and no notion of "already shown but ignored".

---

## Search

`GET /search` answers *"which experiences might match this request?"*. It knows nothing about the
user. Ranking for a person stays in `app/recommender`.

```
"something relaxing under ₹400"
        │  app/search/query.py     parse_query(): traditional NLP
        ▼
text "relaxing"  +  hard filter max_cost=400  +  category hint "wellness"
        │
        ├── keyword_search    PostgreSQL full-text search over a weighted, generated tsvector
        └── semantic_search   cosine similarity between query and stored embeddings
        │
        ▼  reciprocal_rank_fusion: score = Σ 1 / (60 + rank)
ranked hits, each reporting keyword_rank and semantic_rank
```

**Query understanding** uses normalisation, regular expressions and small lexicons rather than a
model, so each constraint can be traced to the phrase that set it, and text it cannot interpret
stays in the search terms instead of becoming a wrong filter. Budget, duration and difficulty are
hard filters. Category is only a hint, since "something relaxing" should not hide a quiet walk.
The UI shows what was understood, so a filter is never invisible. Vague words use documented
assumptions, for example "cheap" means up to ₹500. Known gaps: no spelling correction, no general
negation ("not hiking"), and minimums such as "at least 2 hours" are ignored.

**Embeddings.** `BAAI/bge-small-en-v1.5` via fastembed: 384 dimensions, local ONNX on CPU, about
4 ms per query after a sub-second load, with no API key or usage cost. PyTorch and a hosted API
were rejected for install size and for cost and privacy respectively.

**Why vectors live in an array column.** pgvector is not installed on the development server, and
scanning 42 vectors with NumPy is instant. The measured reason to adopt pgvector and an approximate
index would be this scan becoming slow, not its popularity. `semantic_search` is the only code
that would change.

**Why Reciprocal Rank Fusion.** Keyword scores and cosine similarities have unrelated scales, so
adding them is meaningless. RRF uses positions only and needs no tuning.

**Failure behaviour.** If the model cannot load, or an experience has no vector yet, search still
works through keywords, and the response and UI say so (`mode: "keyword"`).

### Evaluation

`python -m scripts.evaluate_search` scores 24 hand-labelled queries:

| Retriever | Recall@5 | MRR | Answered |
|---|---|---|---|
| keyword | 0.514 | 0.576 | 0.625 |
| semantic | 0.979 | 1.000 | 1.000 |
| hybrid | 0.979 | 0.958 | 1.000 |

- Semantic retrieval is the clear gain: most of the difference comes from paraphrases, where
  keyword search cannot match.
- **Hybrid does not beat semantic alone on this data**, and its MRR is slightly lower. It is kept
  because keyword search handles exact names and rare terms and keeps working if the model fails,
  not because these numbers show better quality.
- Treat these as comparisons, not quality estimates. The developer wrote the labels, the catalogue
  is 42 short items, and `MIN_SIMILARITY` was calibrated on these same queries. Before calibration,
  at 0.62, semantic recall was 0.924.
- Query parsing scored 16/16 on a held-out set, but the same person wrote the rules and the labels,
  so that shows the set was too easy rather than that the parser handles real phrasing.

### Personalised search

`GET /users/{id}/recommendations?q=...` joins the two systems without merging them. Search decides
what may appear, including hard filters. The recommender decides the order for this user, with
`query_match` as half the score. Diversity is off, because the person asked for something specific.
In the UI this is the **Rank for me** action on search results.

### Grounded explanations

Reasons are fixed templates filled from real data. "Similar to Beginner pottery wheel class, which
you saved" takes the title from the catalogue and the verb from the user's current replayed state,
so an undone save is never cited and a reason cannot describe something that does not exist. Tests
assert that every cited title is something the user engaged with.

### Why there is no LLM

An LLM was left out on purpose. Reranking has no real interaction data to be measured against, and
synthetic data would reward whatever matches how it was generated. Explanations are already grounded
and cannot be invented. An LLM would add an API key, per-call cost, latency and a failure mode for no
demonstrated gain. The natural place for one is rewriting explanations or resolving ambiguous
requests, validated against the same structures and falling back to today's deterministic output,
once real usage shows a gap.
