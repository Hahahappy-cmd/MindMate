# MindMate

MindMate is a privacy-conscious mental wellness journal. Users write a title and journal entry, while a local NLP pipeline derives sentiment, subjectivity, detected emotions, dominant emotion, and key phrases. The dashboard presents AI-derived patterns without asking users to label their own mood.

MindMate is a wellness reflection tool, not a medical device and not a substitute for professional care.

## Current features

- Account registration and JWT-based login
- HttpOnly cookie sessions for the browser and bearer tokens for API clients
- CSRF protection for cookie-authenticated mutations
- Journal creation, history, detail, editing, and deletion
- TextBlob sentiment and subjectivity analysis
- Transformer-based multi-label emotion signals with model scores
- Redis/RQ background processing with retries and idempotent entry generations
- Weekly structured summaries
- Dashboard charts for sentiment, emotions, weekday averages, entry frequency, and streaks
- Account data export and deletion
- Automated API, authorization, analytics, NLP, frontend, and security tests

## Stack

- Python 3.11+
- FastAPI and Uvicorn
- SQLAlchemy, PostgreSQL, and psycopg
- Alembic schema migrations
- Redis and RQ
- Pydantic
- Jinja2, Bootstrap, vanilla JavaScript, and Chart.js
- TextBlob and NumPy
- pytest and HTTPX

## Setup

MindMate uses PostgreSQL for development, tests, and production. On macOS with
Homebrew, install and start it, then create separate application and test
databases owned by your local PostgreSQL role:

```bash
brew install postgresql@17
brew services start postgresql@17
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
createdb mindmate
createdb mindmate_test
```

```bash
cd MIndMate
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,worker]'
cp .env.example .env
```

Set `DATABASE_URL` in `.env` for your local role. A passwordless Homebrew local
installation commonly uses:

```env
DATABASE_URL=postgresql+psycopg://YOUR_MACOS_USERNAME@localhost:5432/mindmate
```

Replace both JWT secrets in `.env` with independently generated values. For example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Run

MindMate requires a local Redis server (Redis 5 or newer). Start Redis using your
operating system's service manager, then run the API and worker in separate
terminals:

```bash
# Terminal 1
uvicorn app.main:app --reload

# Terminal 2
python -m app.worker
```

Open:

- Application: <http://127.0.0.1:8000>
- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>
- Dependency readiness: <http://127.0.0.1:8000/ready>

Run `alembic upgrade head` before starting the API or worker after installing or
updating the project. Startup fails if `DATABASE_URL` is missing or does not use
PostgreSQL.

Schema creation and evolution are managed only by Alembic. The application does
not call `create_all()` or alter tables during startup.

## Database and migrations

PostgreSQL is the only supported database. Configure a psycopg SQLAlchemy URL and
apply migrations:

```env
DATABASE_URL=postgresql+psycopg://mindmate:strong-password@localhost:5432/mindmate
```

```bash
alembic upgrade head
alembic current
```

Create a future migration after editing models:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Always inspect generated migrations before applying them. Do not run `alembic
downgrade base` against a database containing data because it removes application
tables.

## Tests

```bash
TEST_DATABASE_URL=postgresql+psycopg://YOUR_MACOS_USERNAME@localhost:5432/mindmate_test python -m pytest
```

The test database name must end in `_test`. The session migrates that dedicated
database from base to head, runs each test inside a rollback transaction, and
downgrades it after the suite. This guard prevents accidental use of the
development or production database.

## Background AI jobs

Creating or editing an entry commits the original writing immediately with an
analysis state of `pending`. The API then adds an RQ job to the `mindmate-ai`
Redis queue and returns without running NLP. The worker moves the entry through
`processing` to `completed`, running TextBlob sentiment, transformer emotions,
and the semantic theme embedding in one idempotent task.

Every edit creates a new analysis generation UUID. The RQ job ID combines the
entry ID and generation, and is enqueued as unique. A worker verifies that
generation before starting and again before storing results, so a slow job cannot
overwrite a newer edit. Repeated completed jobs return without recomputation.

RQ retries failures up to three times with increasing delays. While retries remain,
the entry returns to `pending`; after the final failure it becomes `failed` with a
sanitized message. Redis connection failures are also stored safely on the entry.
Poll `GET /api/entries/{id}/analysis-status` for status. The journal detail page
does this automatically every two seconds while work is active.

The worker uses RQ's in-process `SimpleWorker` so the existing lazy singleton model
instances remain loaded between jobs. Run Redis as a trusted, private service: RQ
job data and application metadata should never be exposed to untrusted clients.

## Security and privacy configuration

Production startup rejects development secrets, insecure cookies, identical access
and refresh secrets, and non-PostgreSQL database URLs. Configure at least:

```env
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://...?sslmode=require
JWT_SECRET_KEY=<independent random value of at least 32 characters>
REFRESH_JWT_SECRET_KEY=<different random value of at least 32 characters>
REDIS_URL=rediss://default:strong-password@redis.example.com:6379/0
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
TRUSTED_HOSTS=journal.example.com
ALLOWED_ORIGINS=https://journal.example.com
PASSWORD_RESET_ENABLED=false
TRUST_PROXY_HEADERS=true
```

Access JWTs include issuer, audience, JTI, expiration, token type, and per-user
session version claims. Refresh JTIs are SHA-256 hashed in the database, rotated on
every refresh, and rejected after replay. Logout and password reset revoke refresh
sessions and invalidate existing access tokens.

Cookie-authenticated mutations require a matching CSRF header/token. Browser
cookies are HttpOnly where appropriate, and production requires Secure cookies.
Responses include CSP, frame, content-type, referrer, permissions, and private
cache-control headers. Request bodies are bounded by `MAX_REQUEST_BYTES`.
Journal content and tokens are not added to operational logs, and all NLP remains
local—no third-party AI service receives journal text.

## Data concepts

MindMate deliberately separates:

- `title` and `content`: the user-authored journal data
- `sentiment_label`, `sentiment_score`, and `sentiment_strength`: TextBlob-derived polarity
- `detected_emotions`, `dominant_emotion`, and `emotional_intensity`: multi-label transformer results

## Emotion analysis

MindMate uses `SamLowe/roberta-base-go_emotions`, a RoBERTa-base model trained for
multi-label classification over the 28 GoEmotions labels (including neutral). The
model is loaded lazily once per application process. Logits are converted with a
sigmoid; labels at or above `EMOTION_THRESHOLD` are returned, capped by
`EMOTION_TOP_N`. If none cross the threshold, the highest-scoring label is returned
so the API has an intentional dominant result.

Sentiment remains a separate TextBlob polarity signal (positive/negative/neutral);
emotion classification supplies categories such as joy, sadness, gratitude, and
optimism. Neither output represents a diagnosis.

Long entries are split into overlapping token windows instead of silently
truncated. Per-window probabilities are combined using a token-count-weighted
mean. Stored analysis includes model name, pinned revision, threshold, score
semantics, chunk count, and timestamp. If the transformer runtime or model files
are unavailable, journal creation falls back to the old keyword detector and
explicitly records `keyword_fallback` / `keyword_match_density`.

These probabilities are model outputs, not clinical confidence or a mental-health
diagnosis. The model was trained on short, general English text; nuance, sarcasm,
demographic bias, domain shift, and long-document aggregation remain limitations.

Run the reproducible 20-example integration evaluation with:

```bash
python -m app.nlp.evaluation
```

It reports micro precision/recall/F1 and macro F1, plus a limited keyword baseline
on the six labels shared by both systems. The fixture is a small hand-authored
engineering check, not a publishable benchmark or evidence of clinical validity.

Run the fast NLP and API tests with `python -m pytest`. Run the separately marked
real-model smoke test with `RUN_SLOW_NLP_TESTS=1 python -m pytest tests/test_nlp.py`.

## Long-term analytics and recurring themes

`GET /api/entries/long-term-analytics?period=30` accepts `7`, `30`, `90`, or
`all`. It returns calendar-based rolling sentiment, current-versus-previous period
comparisons, dominant and multi-label emotion aggregates, weekday patterns, entry
frequency, semantic themes, and statements backed by those aggregates. Three
entries are required before MindMate labels a trend or generates insights.

Recurring themes use the pinned `sentence-transformers/all-MiniLM-L6-v2` model to
create 384-dimensional semantic embeddings. Long entries are embedded as
overlapping chunks and combined into a normalized, token-weighted vector.
Agglomerative cosine clustering groups entries without prespecifying a theme
count. A cluster must contain at least two entries, and its readable label is the
title of the entry closest to the cluster center. This is extractive: MindMate does
not invent a topic name or rely on hard-coded categories.

Embeddings, source hashes, model metadata, and timestamps are stored by the AI
worker. Analytics requests only read completed analysis and never invoke a model.
Semantic similarity can merge distinct subjects or split one subject, and
representative titles are only concise descriptions—not psychological conclusions.

## Project structure

```text
app/
├── AI/                 # Current local NLP and report calculations
├── frontend/           # Jinja templates and browser assets
├── routes/             # User, journal, analytics, and page routes
├── auth.py             # Password hashing and JWT helpers
├── config.py           # Environment-backed settings
├── database.py         # SQLAlchemy engine and development migration
├── dependencies.py     # Authentication and CSRF dependencies
├── main.py             # FastAPI application entry point
├── queue.py            # Redis/RQ connection and enqueue policy
├── jobs.py             # Idempotent AI worker task
├── worker.py           # Long-running model-reusing RQ worker
├── models.py           # SQLAlchemy data model
└── schemas.py          # API contracts
tests/                  # Automated test suite
```

## Free deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the manual Render Free + Neon Free +
Upstash Free + Oracle Always Free A1 deployment sequence. The base installation
contains the web runtime; install `.[worker]` only on the Oracle worker so Render
does not download PyTorch or Transformers.

## Production notes

Production mode requires non-development JWT secrets, secure cookies, encrypted
database/Redis connections, explicit hosts, and a production process manager.

## Pre-deployment operations

Production additionally requires PostgreSQL TLS (`sslmode=require`, `verify-ca`,
or `verify-full`) and authenticated Redis TLS (`rediss://`). Only enable
`TRUST_PROXY_HEADERS` behind a trusted reverse proxy that overwrites forwarded
client-address headers. Authentication limits use configurable Redis fixed
windows; journal CRUD is not limited. Limiter infrastructure failure is
deliberately fail-open so users are not globally locked out, and must be monitored.

Refresh-token rotations retain a family identifier. Replay of any rotated member
revokes all remaining descendants in that family. Password-reset credentials are
stored only as SHA-256 hashes, expire, are one-time use, and supersede older reset
credentials. Because authenticated email delivery is not implemented, production
must keep `PASSWORD_RESET_ENABLED=false`; only development returns a token for
local testing.

Recover a database commit whose AI enqueue failed, or a worker that died while a
job was processing, with the generation-safe reconciliation command:

```bash
python -m app.maintenance recover-analysis
```

Run expired security-record cleanup periodically:

```bash
python -m app.maintenance cleanup-security
```

The defaults retain expired refresh-session records for 30 days and expired reset
records for 7 days. Journal content remains until its owner deletes the entry or
account. RQ results expire after one hour and failures after one day.

For the real queue integration test, use isolated test resources:

```bash
TEST_DATABASE_URL=postgresql+psycopg://YOUR_MACOS_USERNAME@localhost:5432/mindmate_test \
TEST_REDIS_URL=redis://localhost:6379/15 \
python -m pytest tests/test_rq_integration.py
```

Never point test variables at production resources. Store secrets only in
environment variables or a managed secret store; `.env` is ignored. Rotate access
JWT, refresh JWT, PostgreSQL, and Redis credentials independently. JWT-secret
rotation invalidates existing sessions.

Enable encrypted PostgreSQL backups before accepting private writing. Restrict
backup access and retention because backups contain journal content. Regularly
restore into an isolated database, run `alembic current`, compare expected row
counts, test login and an owner-scoped journal read, then securely remove the
verification database. Use a least-privilege application role and, where
available, a separate schema-migration role. Operational logs must not contain
journal content, raw tokens, authorization headers, connection URLs, or backup
credentials.
