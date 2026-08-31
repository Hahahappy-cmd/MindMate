import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import JournalEntry


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
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


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
