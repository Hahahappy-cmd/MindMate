from __future__ import annotations

from functools import lru_cache

from redis import Redis
from rq import Queue, Retry
from rq.exceptions import DuplicateJobError
from rq.serializers import JSONSerializer

from .config import settings


@lru_cache(maxsize=1)
def get_redis_connection() -> Redis:
    return Redis.from_url(settings.redis_url)


@lru_cache(maxsize=1)
def get_ai_queue() -> Queue:
    return Queue(settings.ai_queue_name, connection=get_redis_connection(), serializer=JSONSerializer)


def analysis_job_id(entry_id: int, generation: str) -> str:
    return f"entry-{entry_id}-{generation}"


def enqueue_analysis_job(entry_id: int, generation: str) -> str:
    from .jobs import analyze_journal_entry

    job_id = analysis_job_id(entry_id, generation)
    try:
        retry_intervals = [min(300, 10 * (3 ** index)) for index in range(settings.ai_job_max_retries)]
        get_ai_queue().enqueue(
            analyze_journal_entry,
            entry_id,
            generation,
            job_id=job_id,
            unique=True,
            retry=Retry(max=settings.ai_job_max_retries, interval=retry_intervals),
            job_timeout=settings.ai_job_timeout_seconds,
            result_ttl=3600,
            failure_ttl=86400,
        )
    except DuplicateJobError:
        pass
    return job_id
