import pytest

from app.jobs import analyze_journal_entry
from app.models import JournalEntry
from app.queue import analysis_job_id, enqueue_analysis_job


def create_pending(client, headers, title="Queued entry", content="I feel hopeful today."):
    response = client.post("/api/entries/", headers=headers, json={"title": title, "content": content})
    assert response.status_code == 201
    return response.json()


def test_create_enqueues_unique_generation_job(client, auth_headers, monkeypatch):
    calls = []
    monkeypatch.setattr("app.routes.entries.enqueue_analysis_job", lambda entry_id, generation: calls.append((entry_id, generation)) or analysis_job_id(entry_id, generation))
    entry = create_pending(client, auth_headers)
    assert entry["analysis_state"] == "pending"
    assert entry["sentiment_score"] is None
    assert len(calls) == 1
    assert entry["analysis_job_id"] == analysis_job_id(*calls[0])


def test_worker_completes_and_status_endpoint_updates(client, auth_headers, run_pending_analysis):
    entry = create_pending(client, auth_headers)
    before = client.get(f"/api/entries/{entry['id']}/analysis-status", headers=auth_headers).json()
    assert before["state"] == "pending"
    assert run_pending_analysis(entry["id"]) == "completed"
    after = client.get(f"/api/entries/{entry['id']}/analysis-status", headers=auth_headers).json()
    assert after["state"] == "completed"
    assert after["attempts"] == 1
    assert after["completed_at"] is not None


def test_failure_state_then_retry_succeeds(client, auth_headers, db_session, monkeypatch, run_pending_analysis):
    import app.jobs as jobs

    entry = create_pending(client, auth_headers)
    original = jobs.analyze_entry
    monkeypatch.setattr(jobs, "analyze_entry", lambda _content: (_ for _ in ()).throw(RuntimeError("secret detail")))
    with pytest.raises(RuntimeError):
        run_pending_analysis(entry["id"])
    failed = db_session.get(JournalEntry, entry["id"])
    assert failed.analysis_state == "failed"
    assert "secret detail" not in failed.analysis_error
    assert failed.analysis_attempts == 1

    monkeypatch.setattr(jobs, "analyze_entry", original)
    assert run_pending_analysis(entry["id"]) == "completed"
    assert db_session.get(JournalEntry, entry["id"]).analysis_attempts == 2


def test_failed_attempt_returns_to_pending_when_rq_will_retry(client, auth_headers, db_session, monkeypatch, run_pending_analysis):
    import app.jobs as jobs

    entry = create_pending(client, auth_headers)
    monkeypatch.setattr(jobs, "get_current_job", lambda: type("Job", (), {"retries_left": 2})())
    monkeypatch.setattr(jobs, "analyze_entry", lambda _content: (_ for _ in ()).throw(RuntimeError("temporary")))
    with pytest.raises(RuntimeError):
        run_pending_analysis(entry["id"])
    stored = db_session.get(JournalEntry, entry["id"])
    assert stored.analysis_state == "pending"
    assert "retry scheduled" in stored.analysis_error


def test_completed_job_is_idempotent(client, auth_headers, db_session, run_pending_analysis):
    entry = create_pending(client, auth_headers)
    assert run_pending_analysis(entry["id"]) == "completed"
    assert run_pending_analysis(entry["id"]) == "already_completed"
    assert db_session.get(JournalEntry, entry["id"]).analysis_attempts == 1


def test_edit_supersedes_old_job(client, auth_headers, db_session, monkeypatch):
    import app.jobs as jobs

    monkeypatch.setattr(jobs, "SessionLocal", lambda: db_session)
    entry = create_pending(client, auth_headers)
    old_generation = db_session.get(JournalEntry, entry["id"]).analysis_generation
    updated = client.put(f"/api/entries/{entry['id']}", headers=auth_headers, json={"content": "Updated journal content."})
    assert updated.status_code == 200
    current = db_session.get(JournalEntry, entry["id"])
    assert current.analysis_generation != old_generation
    assert analyze_journal_entry(entry["id"], old_generation) == "stale"
    assert db_session.get(JournalEntry, entry["id"]).analysis_state == "pending"


def test_queue_failure_is_stored_safely(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.routes.entries.enqueue_analysis_job", lambda *_args: (_ for _ in ()).throw(ConnectionError("redis secret")))
    entry = create_pending(client, auth_headers)
    assert entry["analysis_state"] == "pending"
    assert "waiting to be queued" in entry["analysis_error"]
    assert "redis secret" not in entry["analysis_error"]


def test_rq_job_has_retry_timeout_and_duplicate_protection(monkeypatch):
    captured = {}

    class FakeQueue:
        def enqueue(self, function, *args, **kwargs):
            captured.update({"function": function, "args": args, **kwargs})

    monkeypatch.setattr("app.queue.get_ai_queue", lambda: FakeQueue())
    job_id = enqueue_analysis_job(42, "generation")
    assert job_id == "entry-42-generation"
    assert captured["unique"] is True
    assert captured["retry"].max == 3
    assert captured["job_timeout"] == 600
