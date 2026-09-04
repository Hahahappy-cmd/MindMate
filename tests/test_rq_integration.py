import os
import uuid

import pytest
from redis import Redis
from rq import Queue, SimpleWorker
from rq.serializers import JSONSerializer

from app.database import SessionLocal
from app.jobs import analyze_journal_entry
from app.models import JournalEntry, User
from app.auth import get_password_hash


@pytest.mark.integration
def test_real_redis_rq_worker_writes_postgresql(monkeypatch):
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("Set TEST_REDIS_URL to an isolated real Redis database")
    redis = Redis.from_url(redis_url)
    redis.ping()
    queue = Queue(f"mindmate-test-{uuid.uuid4()}", connection=redis, serializer=JSONSerializer)
    db = SessionLocal()
    username = f"rq-{uuid.uuid4().hex}"
    observed_states = []
    try:
        user = User(username=username, email=f"{username}@example.com", hashed_password=get_password_hash("test-password"))
        db.add(user)
        db.commit()
        entry = JournalEntry(
            user_id=user.id, title="RQ integration", content="I feel hopeful today.",
            analysis_state="pending", analysis_generation=str(uuid.uuid4()),
        )
        db.add(entry)
        db.commit()
        entry_id, generation = entry.id, entry.analysis_generation

        import app.jobs as jobs
        original = jobs.analyze_entry

        def observe_processing(content):
            check = SessionLocal()
            try:
                observed_states.append(check.get(JournalEntry, entry_id).analysis_state)
            finally:
                check.close()
            return original(content)

        monkeypatch.setattr(jobs, "analyze_entry", observe_processing)
        job = queue.enqueue(analyze_journal_entry, entry_id, generation, job_timeout=120)
        assert db.get(JournalEntry, entry_id).analysis_state == "pending"
        worker = SimpleWorker([queue], connection=redis, serializer=JSONSerializer)
        assert worker.work(burst=True, with_scheduler=False)
        db.expire_all()
        completed = db.get(JournalEntry, entry_id)
        assert observed_states == ["processing"]
        assert completed.analysis_state == "completed"
        assert completed.sentiment_score is not None
        job.refresh()
        assert job.is_finished
    finally:
        queue.empty()
        user = db.query(User).filter_by(username=username).first()
        if user:
            db.delete(user)
            db.commit()
        db.close()
