# L.I.V.E

**Learn · Interact · Venture · Experience.** A platform that recommends *actionable experiences*
(things to do, learn, try) instead of passive content, and learns from what people actually do.

The product vision is in [docs/VISION.md](docs/VISION.md). This README is the technical guide.

## What it does

```
Discover ──► Interact ──► Record feedback ──► Understand preferences
   ▲                                                   │
   └── Rank recommendations ◄── Retrieve experiences ◄─┘
```

- **Natural-language search:** "something relaxing under ₹400" becomes a budget filter plus a
  meaning-based search, and the UI shows what was understood.
- **Hybrid retrieval:** PostgreSQL full-text search and local embeddings, merged with Reciprocal
  Rank Fusion, falling back to keywords if the model is unavailable.
- **Personalised recommendations:** an explainable feature-based ranker built from an append-only
  event log, with honest cold-start handling.
- **Grounded explanations:** every reason comes from real data, for example "similar to Beginner
  pottery wheel class, which you saved".
- **Measured:** offline evaluation for ranking and retrieval, plus backend and browser tests in CI.

Quality figures in this README come from synthetic data and developer-written labels. They compare
methods against each other and do not show real-world quality.

### Five-minute demo

Run the app (see [Setup](#setup)), then:

1. Pick `demo_outdoor_maya`, then `demo_creative_lena`. Recommendations follow each history.
2. Click the example search **ceramics**: it finds pottery with no shared words.
3. Click **something relaxing under ₹400**: see the budget understood and enforced.
4. On the results, click **Rank for me** to reorder them for this user.
5. Pick `demo_coldstart_ella`: popular picks, labelled as not personalised.
6. Save and like a few things as Ella: the section becomes personalised, with reasons.
7. Open **My history**: every action, as stored in the event log.

Reset the demo with `python -m scripts.seed --reset`. Deployment is covered in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Architecture

```
 Browser
    │  (React client components, demo-user picker)
    ▼
 Next.js 16 (frontend/)          lib/api.ts ── the only module that calls fetch()
    │  REST / JSON over HTTP     lib/events.ts ── event helpers + state derived from the log
    ▼
 FastAPI (backend/app/)
    main.py ── CORS, includes routers
    routers/users.py · experiences.py · interactions.py · recommendations.py · search.py
    search/ ── query understanding, keyword and semantic retrieval, fusion
    recommender/ ── profile → candidates → features → score → diversify → explain
    dependencies.py ── DbSession (Depends(get_db)), get_or_404, ExistingUser, pagination
    schemas.py ── Pydantic request (validate) / response (serialise) models
    │  SQLAlchemy 2.x ORM, psycopg 3
    ▼
 PostgreSQL
    users ─────────┐
    experiences ───┤
    interactions ──┘  append-only event log (FK → users, FK → experiences)
    alembic_version   which migration is applied
```

**Layers.** Routers handle HTTP (status codes, 404/409). Pydantic schemas validate what clients
send and shape what they receive. ORM models describe tables. The database enforces the same
invariants again with constraints, so no write path can store invalid events.

## Repository layout

```
backend/
  app/            FastAPI application (config, database, models, enums, schemas, routers)
  app/search/       query understanding and hybrid retrieval
  app/recommender/  recommendation engine (pure pipeline + DB-loading service)
  alembic/        migrations (versions/*.py)
  scripts/seed.py      demo data for the development database
  scripts/evaluate.py  offline recommender evaluation (read-only)
  tests/          pytest: schemas, API, database, seed, recommender, evaluation (isolated test database)
frontend/
  app/            pages: / (catalogue), /experiences/[id], /history
  components/     cards, header, demo-user context, data hooks
  lib/            api client, event helpers, types, formatting
docs/VISION.md    product vision
```

## Setup

Requirements: Python 3.13, Node 22, PostgreSQL 16+ (developed on 18).

### 1. PostgreSQL

Create the development database (the test database is created automatically by pytest):

```sql
CREATE DATABASE live_db;
```

### 2. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt  # locked app deps + test tools
copy .env.example .env               # then edit both URLs (URL-encode special characters, "@" -> "%40")
alembic upgrade head                 # create tables
python -m scripts.seed               # demo users, experiences, interaction histories
python -m scripts.embed_experiences  # vectors for semantic search (downloads ~70 MB once)
uvicorn app.main:app --reload        # http://127.0.0.1:8000, docs at /docs
```

`backend/.env` (git-ignored):

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | app, Alembic, seed | `postgresql+psycopg://USER:PASSWORD@localhost:5432/live_db` |
| `CORS_ORIGINS` | app | optional locally; comma-separated origins allowed to call the API |
| `TEST_DATABASE_URL` | pytest and Playwright | must name a different database ending in `_test`; **dropped and recreated on every test run** |

### 3. Frontend

```powershell
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

Optional `frontend/.env.local`: `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`). It is
inlined into the browser bundle at build time, so it must never contain secrets. The backend's CORS
setting allows `http://localhost:3000` and `http://127.0.0.1:3000`.

## Database migrations (Alembic)

```powershell
alembic current                                  # applied revision
alembic upgrade head                             # apply all migrations
alembic downgrade -1                             # undo the latest one
alembic revision --autogenerate -m "describe change"   # draft a migration from model changes
alembic check                                    # fails if models and database differ
```

Always read an autogenerated migration before applying it. Autogenerate does not compare server
defaults or CHECK-constraint text, and can mistake a rename for drop + add.
`alembic/env.py` takes the URL from `DATABASE_URL` and escapes `%` for configparser.

| Revision | Change |
|---|---|
| `fd7484a41540` | `experiences` table |
| `06797c060046` | `users`, `interactions` (+ CHECKs, FKs, indexes); `experiences.created_at`; `cost` server default |
| `b3f1a9c27d10` | generated `search_vector` with a GIN index; `embedding`, `embedding_model` |

## Seed data

```powershell
python -m scripts.seed           # create whatever demo data is missing (safe to re-run)
python -m scripts.seed --reset   # also rebuild the demo users' interaction histories
```

- 42 experiences across `outdoors`, `adventure`, `creative`, `social`, `learning` and `wellness`.
- 14 users named `demo_*`, with scripted behaviour profiles: outdoor, adventure, creative ×2,
  social ×2, wellness ×2, learning ×2, mixed ×2, and **2 cold-start users with no events**.
- About 340 interactions over the last 70 days. Loved categories get
  `view → click → save → like → complete` (with occasional `unsave`), tolerated ones get
  `view → click (→ save)`, avoided ones get `view → skip/dislike`. Each profile also has a search.
- Deterministic: a per-user seeded RNG produces the same histories on every run.
- Safety: refuses databases whose name ends in `_test`. It only touches `demo_*` users and its own
  catalogue titles, and only generates a history for a demo user who has none.

## Tests

```powershell
cd backend
pytest                    # whole suite
pytest tests/test_api_interactions.py -v
```

| File | Covers |
|---|---|
| `test_schemas.py` | Pydantic validation rules (no database) |
| `test_api_users.py`, `test_api_experiences.py`, `test_api_interactions.py` | the HTTP API through FastAPI's `TestClient` |
| `test_database.py` | constraints, FKs, cascade, JSONB, schema built by Alembic, isolation |
| `test_seed.py` | seed safety, idempotence, determinism, profile coherence |
| `test_e2e_server.py` | the browser-test database guard |
| `test_api_reliability.py` | hostile input, database outage and mid-request deletion produce clean errors |
| `test_query_understanding.py`, `test_search.py` | constraint extraction, fusion, keyword and semantic retrieval, filters, fallback (with a fake embedder) |
| `test_recommender.py`, `test_api_recommendations.py`, `test_evaluation.py` | see [Testing the recommender](#10-testing-the-recommender) |
| `test_config.py` | deployment settings and the health check |

**Isolation.** `tests/conftest.py` refuses to run unless `TEST_DATABASE_URL` is set, ends in `_test`
and differs from `DATABASE_URL`. It then sets `DATABASE_URL` to the test URL *before* importing the
app, so the app's own engine points at the test database. Once per run, the test database is
dropped, recreated and migrated with `alembic upgrade head`. Each test runs in a transaction
that is rolled back (`join_transaction_mode="create_savepoint"` turns the routes' `commit()` into
`RELEASE SAVEPOINT`), and `get_db` is overridden to hand the routes that same session.

Frontend checks: `npm run lint`, `npx tsc --noEmit`, `npm run build`.

### Browser tests (Playwright)

```powershell
cd frontend
npx playwright install chromium   # first time only
npm run test:e2e
```

**Stop your dev servers first.** Playwright starts its own servers on ports 3000 and 8000 and
deliberately refuses to reuse a running one, because a dev server is connected to `live_db`.

`backend/scripts/e2e_server.py` derives a third database, `live_db_e2e`, from `TEST_DATABASE_URL`,
then drops, migrates and seeds it on every run. It refuses any name not ending in `_e2e`. Each
test that writes data creates its own user, and failures are simulated by intercepting network
requests. Tests live in `frontend/e2e/`.

| Database | Used by | Lifetime |
|---|---|---|
| `live_db` | the app in development | permanent; never touched by tests |
| `live_db_test` | `pytest` | recreated each run |
| `live_db_e2e` | Playwright | recreated each run |

### Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`: backend tests and
migration checks, frontend lint, type-check and build, and the browser suite, each against a
temporary PostgreSQL 18 container using throwaway credentials.

### Updating Python dependencies

`requirements.in` and `requirements-dev.in` list what the project needs directly. The `.txt` files
are generated locks with every exact version, so do not edit them by hand.

```powershell
pip-compile requirements.in -o requirements.txt              # after editing a .in file
pip-compile requirements-dev.in -o requirements-dev.txt
pip-compile --upgrade requirements.in -o requirements.txt    # deliberately take newer versions
```

## API

Interactive docs: `http://127.0.0.1:8000/docs`. List endpoints take `limit` (1–100, default 50)
and `offset` (≥ 0).

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| GET | `/` | – | 200 welcome message | |
| GET | `/health` | – | 200 if the database answers | 503 |
| POST | `/users` | `{username}` (3–50 chars, `[A-Za-z0-9_]`) | 201 user | 409 taken, 422 |
| GET | `/users` | – | 200 list (id order) | 422 |
| GET | `/users/{user_id}` | – | 200 user | 404, 422 |
| POST | `/experiences` | title, description, category, difficulty, duration_minutes (>0), cost (≥0, default 0) | 201 experience | 422 |
| GET | `/experiences` | – | 200 list (id order) | 422 |
| GET | `/experiences/{experience_id}` | – | 200 experience | 404, 422 |
| POST | `/users/{user_id}/interactions` | `{event_type, experience_id?, query_text?, properties?}` | 201 event | 404 user/experience, 422 |
| GET | `/users/{user_id}/interactions` | – | 200 list, newest first | 404, 422 |
| GET | `/users/{user_id}/interactions/state` | – | 200 current saved/liked/disliked/completed/skipped per experience, from the whole log | 404, 422 |
| GET | `/users/{user_id}/recommendations` | – (`limit` 1–50, default 10) | 200 ranked list + strategy + reasons; `q` ranks search results for the user | 404, 422 |
| GET | `/search` | – (`q`, `category`, `difficulty`, `max_cost`, `max_duration_minutes`) | 200 hits + how the query was understood | 422 |

Unknown fields are rejected (`422 extra_forbidden`), so clients cannot set `id`, `user_id`,
`created_at` or `occurred_at`. Integers must be real JSON integers. Errors use FastAPI's format:
`{"detail": "..."}`, or a list of validation errors for 422. Path dependencies run before body
validation, so a bad body sent to an unknown user returns 404.

## Interaction / event model

`interactions` is an **append-only log**: one row per action, never updated. Current state, such as
"is this saved?", is derived by replaying events. `app/recommender/state.py` is the one place that
defines how: each event type counts once per experience at its latest time, `unsave`/`unlike` remove
what they reverse, `like` and `dislike` replace each other, and a positive action clears a `skip`.
The log keeps everything that happened; this is only how it is interpreted, so repeated clicks
cannot inflate a preference and old data is corrected without rewriting it.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `user_id` | FK → users, `ON DELETE CASCADE` | taken from the URL, never from the body |
| `experience_id` | FK → experiences, nullable, cascade | NULL only for `search` |
| `event_type` | varchar(32) + CHECK | one of the 10 types below |
| `query_text` | text, nullable | required for `search`, forbidden otherwise |
| `properties` | JSONB, nullable | flat map ≤ 20 keys, scalar values, e.g. `{"source":"catalogue","position":3}` |
| `occurred_at` | timestamptz, server default `now()` | set by the server |

| Event | Kind | Meaning |
|---|---|---|
| `view` | implicit | experience detail shown |
| `click` | implicit | opened from a list (`properties.position` = rank in that list) |
| `save` / `unsave` | implicit | bookmark toggled (reversal recorded as its own event) |
| `like` / `unlike` | explicit | positive feedback toggled |
| `dislike` | explicit | negative feedback |
| `complete` | implicit (strong) | user did the experience |
| `skip` | implicit (negative) | "not for me" |
| `search` | intent | free-text query, no experience |

Rules are enforced twice: in `InteractionCreate` (Pydantic, for clear 422 messages) and in the
CHECK constraints `ck_interactions_event_type_valid` / `ck_interactions_event_shape` (the
database's guarantee). Indexes: `(user_id, occurred_at)` for history,
`(experience_id, event_type)` for popularity.

## How a frontend action reaches PostgreSQL

```
click "Save" on a card (components/ExperienceCard.tsx)
  → page's onEvent → useActivity().record({event_type: "save", experience_id, properties: {source, position}})
  → lib/api.ts createInteraction → POST {API_URL}/users/{id}/interactions   (no user_id in body)
  → FastAPI: CORS → interactions router → ExistingUser dependency (404?) → InteractionCreate (422?)
           → experience exists? (404) → INSERT INTO interactions … → 201 + JSON
  → useActivity prepends the returned event → deriveState() recomputes saved/liked → button shows "Saved ✓"
```

Frontend event sources: title link → `click`, detail page mount → `view` (guarded against React
Strict Mode's double effect), card/detail buttons → `save/unsave/like/unlike/dislike/complete/skip`,
search form → `search`. The `/history` page reads `GET /users/{id}/interactions`.

**Demo mode.** There is no authentication: the header dropdown picks which user you act as, and
any client can post events for any user. That is deliberate for a demo; real authentication must come first for real users.

---

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
