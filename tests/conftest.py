import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

test_database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not test_database_url:
    raise RuntimeError("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test")
parsed_test_url = make_url(test_database_url.replace("postgresql://", "postgresql+psycopg://", 1))
if parsed_test_url.get_backend_name() != "postgresql" or not (parsed_test_url.database or "").endswith("_test"):
    raise RuntimeError("Tests require a PostgreSQL database whose name ends in _test")
os.environ["DATABASE_URL"] = test_database_url

from app.database import get_db
from app.main import app
from app.models import JournalEntry


class FakeRateRedis:
    def __init__(self):
        self.values = {}

    def eval(self, _script, _key_count, key, _seconds):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


@pytest.fixture(autouse=True)
def isolated_rate_limiter(monkeypatch):
    fake = FakeRateRedis()
    monkeypatch.setattr("app.rate_limit.get_redis_connection", lambda: fake)
    return fake


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield
    command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def stub_transformer(monkeypatch):
    """Keep the normal suite fast and deterministic; real inference is a slow test."""
    def analyze(_text):
        return {
            "dominant_emotion": "joy",
            "emotions": {"joy": 0.82, "optimism": 0.61},
            "model_name": "test/go-emotions",
            "model_version": "test-revision",
            "analysis_method": "transformer",
            "score_semantics": "sigmoid_probability",
            "threshold": 0.5,
            "chunks_analyzed": 1,
        }
    monkeypatch.setattr("app.services.analysis.analyze_emotions", analyze)

    class ThemeEmbedderStub:
        model_name = "test/minilm"
        model_version = "test-revision"

        def embed(self, text):
            lowered = text.lower()
            if "school" in lowered or "exam" in lowered:
                return [1.0, 0.0, 0.0]
            if "work" in lowered or "office" in lowered:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

    monkeypatch.setattr("app.jobs.get_theme_embedder", lambda: ThemeEmbedderStub())
    monkeypatch.setattr("app.routes.entries.enqueue_analysis_job", lambda entry_id, generation: f"entry-{entry_id}-{generation}")


@pytest.fixture()
def db_session():
    from app.database import engine

    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, autocommit=False, autoflush=False, expire_on_commit=False, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def run_pending_analysis(db_session, monkeypatch):
    import app.jobs as jobs

    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)

    def run(entry_id):
        entry = db_session.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        return jobs.analyze_journal_entry(entry_id, entry.analysis_generation)

    return run


@pytest.fixture()
def registered_user(client):
    payload = {"email": "alex@example.com", "username": "alex", "password": "correct-horse"}
    response = client.post("/api/users/register", json=payload)
    assert response.status_code == 200
    return payload


@pytest.fixture()
def auth_headers(client, registered_user):
    response = client.post("/api/users/login", json={"username": registered_user["username"], "password": registered_user["password"]})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
