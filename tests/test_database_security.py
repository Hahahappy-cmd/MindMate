import pytest
from sqlalchemy import create_mock_engine, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable
from pydantic import ValidationError

from app import models
from app.database import engine, normalize_database_url
from app.config import Settings


def test_refresh_rotation_rejects_replay(client, registered_user):
    login = client.post("/api/users/login", json={"username": "alex", "password": "correct-horse"}).json()
    rotated = client.post("/api/users/refresh", json={"refresh_token": login["refresh_token"]})
    assert rotated.status_code == 200
    assert client.post("/api/users/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
    assert client.post("/api/users/refresh", json={"refresh_token": rotated.json()["refresh_token"]}).status_code == 401


def test_api_logout_invalidates_access_and_refresh(client, registered_user):
    login = client.post("/api/users/login", json={"username": "alex", "password": "correct-horse"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.post("/api/users/logout", headers=headers).status_code == 200
    assert client.get("/api/users/me", headers=headers).status_code == 401
    assert client.post("/api/users/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401


def test_account_deletion_cascades_private_data(client, auth_headers, db_session):
    client.post("/api/entries/", headers=auth_headers, json={"title": "Private", "content": "private content"})
    response = client.request("DELETE", "/api/users/me", headers=auth_headers, json={"password": "correct-horse"})
    assert response.status_code == 204
    assert db_session.query(models.User).count() == 0
    assert db_session.query(models.JournalEntry).count() == 0
    assert db_session.query(models.RefreshSession).count() == 0


def test_export_is_scoped_to_current_user(client, auth_headers):
    client.post("/api/entries/", headers=auth_headers, json={"title": "Mine", "content": "private"})
    exported = client.get("/api/users/export", headers=auth_headers).json()
    assert [entry["title"] for entry in exported["entries"]] == ["Mine"]


def test_security_headers_request_limit_and_host(client):
    response = client.get("/api/")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/users/register", content=b"x" * 300000).status_code == 413
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400


def test_readiness_checks_postgresql_and_redis(client, monkeypatch):
    monkeypatch.setattr("app.main.get_redis_connection", lambda: type("Redis", (), {"ping": lambda self: True})())
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"postgresql": True, "redis": True}}


def test_database_constraints(db_session, registered_user):
    user = db_session.query(models.User).one()
    db_session.add(models.JournalEntry(title="Bad", content="Bad", user_id=user.id, analysis_state="unknown", analysis_attempts=0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_models_compile_for_postgresql_and_use_jsonb():
    dialect = create_mock_engine("postgresql+psycopg://", lambda *_args, **_kwargs: None).dialect
    sql = str(CreateTable(models.JournalEntry.__table__).compile(dialect=dialect))
    assert "JSONB" in sql
    assert isinstance(models.JournalEntry.emotion_data.type.dialect_impl(dialect), JSONB)
    assert normalize_database_url("postgresql://user:pass@db/name").startswith("postgresql+psycopg://")


def test_production_configuration_fails_closed():
    with pytest.raises(RuntimeError):
        Settings(environment="production", database_url="mysql://db/mindmate", _env_file=None).validate_production()
    secure = Settings(
        environment="production", database_url="postgresql://user:pass@db/mindmate?sslmode=require",
        redis_url="rediss://default:secret@redis.example.com:6379/0", password_reset_enabled=False,
        jwt_secret_key="a" * 48, refresh_jwt_secret_key="b" * 48,
        cookie_secure=True, trusted_hosts="journal.example.com", _env_file=None,
    )
    secure.validate_production()


def test_production_rejects_insecure_database_and_redis_urls():
    common = dict(
        environment="production", jwt_secret_key="a" * 48, refresh_jwt_secret_key="b" * 48,
        cookie_secure=True, trusted_hosts="journal.example.com", password_reset_enabled=False, _env_file=None,
    )
    with pytest.raises(RuntimeError, match="PostgreSQL TLS"):
        Settings(database_url="postgresql://user:pass@db/mindmate", redis_url="rediss://default:secret@redis:6379", **common).validate_production()
    with pytest.raises(RuntimeError, match="authenticated rediss"):
        Settings(database_url="postgresql://user:pass@db/mindmate?sslmode=require", redis_url="redis://redis:6379/0", **common).validate_production()


def test_database_url_is_required_and_must_be_postgresql(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        Settings(database_url="mysql://db/mindmate", _env_file=None).validate_production()


def test_alembic_schema_is_at_head_on_postgresql():
    assert engine.dialect.name == "postgresql"
    tables = set(inspect(engine).get_table_names())
    assert {"users", "journal_entries", "refresh_sessions", "password_reset_tokens", "alembic_version"} <= tables
