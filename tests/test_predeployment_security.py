from datetime import datetime, timedelta, timezone

from app import auth, models
from app.services.job_recovery import recover_stale_analysis_jobs
from app.services.retention import cleanup_expired_security_records
from app.rate_limit import client_address


def test_login_rate_limit_allows_then_blocks(client, registered_user, monkeypatch):
    monkeypatch.setattr("app.config.settings.rate_limit_login", "2/60")
    assert client.post("/api/users/login", json={"username": "alex", "password": "wrong"}).status_code == 401
    assert client.post("/api/users/login", json={"username": "alex", "password": "wrong"}).status_code == 401
    blocked = client.post("/api/users/login", json={"username": "alex", "password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many attempts. Please try again later."}
    assert blocked.headers["retry-after"] == "60"


def test_refresh_rotation_replay_revokes_family(client, registered_user, db_session):
    original = client.post("/api/users/login", json={"username": "alex", "password": "correct-horse"}).json()["refresh_token"]
    replacement = client.post("/api/users/refresh", json={"refresh_token": original}).json()["refresh_token"]
    family_ids = {row.family_id for row in db_session.query(models.RefreshSession).all()}
    assert len(family_ids) == 1
    assert client.post("/api/users/refresh", json={"refresh_token": original}).status_code == 401
    assert client.post("/api/users/refresh", json={"refresh_token": replacement}).status_code == 401
    assert all(row.revoked_at is not None for row in db_session.query(models.RefreshSession).all())


def test_password_reset_is_hashed_one_time_and_revokes_sessions(client, registered_user, db_session):
    login = client.post("/api/users/login", json={"username": "alex", "password": "correct-horse"}).json()
    requested = client.post("/api/users/password-reset-request", json={"email": "alex@example.com"})
    raw_token = requested.json()["development_reset_token"]
    stored = db_session.query(models.PasswordResetToken).one()
    assert stored.token_hash == auth.hash_opaque_token(raw_token)
    assert raw_token not in stored.token_hash
    response = client.post("/api/users/password-reset", json={"token": raw_token, "new_password": "new-correct-horse"})
    assert response.status_code == 200
    assert stored.used_at is not None
    assert client.post("/api/users/password-reset", json={"token": raw_token, "new_password": "another-password"}).status_code == 400
    assert client.post("/api/users/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
    assert client.post("/api/users/login", json={"username": "alex", "password": "new-correct-horse"}).status_code == 200


def test_new_reset_request_revokes_previous_token(client, registered_user, db_session):
    first = client.post("/api/users/password-reset-request", json={"email": "alex@example.com"}).json()["development_reset_token"]
    second = client.post("/api/users/password-reset-request", json={"email": "alex@example.com"}).json()["development_reset_token"]
    assert client.post("/api/users/password-reset", json={"token": first, "new_password": "new-password-1"}).status_code == 400
    assert client.post("/api/users/password-reset", json={"token": second, "new_password": "new-password-2"}).status_code == 200


def test_expired_password_reset_token_is_rejected(client, registered_user, db_session):
    raw = "expired-high-entropy-token"
    user = db_session.query(models.User).filter_by(username="alex").one()
    db_session.add(models.PasswordResetToken(
        token_hash=auth.hash_opaque_token(raw), user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    ))
    db_session.commit()
    assert client.post("/api/users/password-reset", json={"token": raw, "new_password": "new-password"}).status_code == 400


def test_production_password_reset_is_not_public(client, registered_user, monkeypatch):
    monkeypatch.setattr("app.config.settings.environment", "production")
    requested = client.post("/api/users/password-reset-request", json={"email": "alex@example.com"})
    assert requested.status_code == 200
    assert "development_reset_token" not in requested.json()
    assert client.post("/api/users/password-reset", json={"token": "anything", "new_password": "new-password"}).status_code == 404


def test_forwarded_address_is_only_trusted_when_configured(monkeypatch):
    request = type("Request", (), {
        "headers": {"x-forwarded-for": "203.0.113.10, 10.0.0.1"},
        "client": type("Client", (), {"host": "127.0.0.1"})(),
    })()
    monkeypatch.setattr("app.config.settings.trust_proxy_headers", False)
    assert client_address(request) == "127.0.0.1"
    monkeypatch.setattr("app.config.settings.trust_proxy_headers", True)
    assert client_address(request) == "203.0.113.10"


def test_recovery_requeues_stale_generation_once(db_session, registered_user, monkeypatch):
    user = db_session.query(models.User).filter_by(username="alex").one()
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    entry = models.JournalEntry(
        user_id=user.id, title="Recover", content="Queued safely", analysis_state="pending",
        analysis_generation="generation-1", analysis_queued_at=old,
    )
    db_session.add(entry)
    db_session.commit()
    calls = []
    monkeypatch.setattr("app.services.job_recovery.enqueue_analysis_job", lambda entry_id, generation, replace_terminal=False: calls.append((entry_id, generation, replace_terminal)) or "job-id")
    result = recover_stale_analysis_jobs(db_session)
    assert result == {"examined": 1, "recovered": 1, "failed": 0}
    assert calls == [(entry.id, "generation-1", True)]
    assert recover_stale_analysis_jobs(db_session)["examined"] == 0


def test_security_record_cleanup_obeys_retention(db_session, registered_user, monkeypatch):
    user = db_session.query(models.User).filter_by(username="alex").one()
    old = datetime.now(timezone.utc) - timedelta(days=60)
    db_session.add(models.RefreshSession(jti_hash="a" * 64, family_id="family", user_id=user.id, expires_at=old))
    db_session.add(models.PasswordResetToken(token_hash="b" * 64, user_id=user.id, expires_at=old))
    db_session.commit()
    result = cleanup_expired_security_records(db_session)
    assert result == {"refresh_sessions_deleted": 1, "reset_tokens_deleted": 1}


def test_csp_uses_nonce_for_inline_scripts(client):
    response = client.get("/")
    csp = response.headers["content-security-policy"]
    script_policy = csp.split("script-src", 1)[1].split(";", 1)[0]
    assert "nonce-" in script_policy
    assert "unsafe-inline" not in script_policy
