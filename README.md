# MindMate

MindMate is a privacy-conscious mental wellness journal. Users write a title and journal entry, while a local NLP pipeline derives sentiment, subjectivity, detected emotions, dominant emotion, and key phrases. The dashboard presents AI-derived patterns without asking users to label their own mood.

MindMate is a wellness reflection tool, not a medical device and not a substitute for professional care.

## Current features

- Account registration and JWT-based login
- HttpOnly cookie sessions for the browser and bearer tokens for API clients
- CSRF protection for cookie-authenticated mutations
- Journal creation, history, detail, editing, and deletion
- TextBlob sentiment and subjectivity analysis
- Rule-based multi-emotion signals with transparent scores
- Weekly structured summaries
- Dashboard charts for sentiment, emotions, weekday averages, entry frequency, and streaks
- Account data export and deletion
- Automated API, authorization, analytics, NLP, frontend, and security tests

## Stack

- Python 3.11+
- FastAPI and Uvicorn
- SQLAlchemy and SQLite
- Pydantic
- Jinja2, Bootstrap, vanilla JavaScript, and Chart.js
- TextBlob and NumPy
- pytest and HTTPX

## Setup

```bash
cd MIndMate
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Replace both JWT secrets in `.env` with independently generated values. For example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Run

```bash
uvicorn app.main:app --reload
```

Open:

- Application: <http://127.0.0.1:8000>
- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

The development database is created as `mindmate.db`. Existing pre-migration databases receive the additive journal fields automatically.

## Tests

```bash
python -m pytest
```

Tests use an isolated in-memory SQLite database and do not modify development journal data.

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
- `analysis_confidence`: unset because the current implementation has no calibrated probability

The current emotion classifier is intentionally lightweight and should not be interpreted as clinical analysis. Its service boundary is designed to allow a versioned model to replace it later.

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
├── models.py           # SQLAlchemy data model
└── schemas.py          # API contracts
tests/                  # Automated test suite
```

## Production notes

Production mode requires non-development JWT secrets and secure cookies. Before a public deployment, the next infrastructure steps are Alembic migrations, PostgreSQL, refresh-session revocation, rate limiting, a production process manager, and CI/CD.
