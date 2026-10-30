# Deploying L.I.V.E

The API and database run on Render and the frontend on Vercel. Any host that runs Python and
Next.js and offers PostgreSQL works the same way; these two are one simple option.

> **Status.** The configuration was tested locally as a production build on other ports (see
> [What has been verified](#what-has-been-verified)). `render.yaml` has not been run on a real Render
> account, so expect to check its plan names and settings against Render's current options.

## Before making it public

**This is a demo deployment.** There is no authentication: anyone with the URL can act as any
demo user, create users and experiences, and post events. There is no rate limiting either. Use
demo data only. Real user accounts and real personal data must wait for authentication.

## 1. Backend and database (Render)

1. Push the repository to GitHub.
2. In Render, choose **New > Blueprint** and select the repository. It reads `render.yaml` and
   creates the API and the database.
3. When asked for `CORS_ORIGINS`, enter a placeholder such as `https://example.com`. You replace it
   in step 3.
4. After the first deploy, open `https://<your-api>.onrender.com/health`. It should return
   `{"status":"ok"}`. `/docs` shows the API.

Each start runs `alembic upgrade head`, the seed script and the embedding script. All three are safe
to repeat. Once you have real data, remove `python -m scripts.seed` from `startCommand`.

## 2. Frontend (Vercel)

1. Import the repository in Vercel and set **Root Directory** to `frontend`.
2. Add the environment variable `NEXT_PUBLIC_API_URL` = `https://<your-api>.onrender.com`.
3. Deploy.

`NEXT_PUBLIC_` values are copied into the browser bundle **at build time**. If the API URL changes,
redeploy the frontend. Never put a secret in one.

## 3. Connect them

In Render, set `CORS_ORIGINS` to your exact frontend origin, for example
`https://live-demo.vercel.app`, with no trailing slash. Separate several origins with commas.
Without this, the browser blocks every API call and the app reports that it cannot reach the backend.

## Environment variables

| Variable | Where | Required | Purpose |
|---|---|---|---|
| `DATABASE_URL` | API | yes | PostgreSQL connection. `postgres://` URLs are accepted and converted |
| `CORS_ORIGINS` | API | yes in production | Comma-separated browser origins allowed to call the API |
| `FASTEMBED_CACHE_PATH` | API | no | Where the embedding model is stored |
| `TEST_DATABASE_URL` | CI and local only | for tests | Never set this in production |
| `NEXT_PUBLIC_API_URL` | frontend build | yes in production | Public URL of the API |

Secrets belong in the host's environment settings. Never commit them.

## Updating a running deployment

Pushing to the deployed branch rebuilds both services. Migrations run at start. Before deploying a
migration that removes or renames anything, take a database backup, since `alembic downgrade` cannot
restore dropped data.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Cannot reach the L.I.V.E backend" | `NEXT_PUBLIC_API_URL` wrong, `CORS_ORIGINS` missing the frontend origin, or the API is asleep or down |
| Search says "keywords only" | The model failed to load, or `embed_experiences` has not run |
| `/health` returns 503 | The API cannot reach the database |
| Service restarts under load | Out of memory; the app needs a plan with at least 512 MB |

## What has been verified

Locally, with a production Next.js build served on port 3100, the API on port 8100 and the
disposable `live_db_e2e` database:

- the frontend bundle called the configured API URL rather than the default;
- the API accepted the configured origin and rejected others;
- `/health` responded, and migrations, seeding and embedding ran through the start sequence.

Not verified: a real Render or Vercel deployment, real TLS, and memory limits on a real instance.
