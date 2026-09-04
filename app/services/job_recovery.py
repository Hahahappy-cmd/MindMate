from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import settings
from ..models import JournalEntry
from ..queue import enqueue_analysis_job

logger = logging.getLogger(__name__)


def recover_stale_analysis_jobs(db: Session, *, now: datetime | None = None, limit: int = 100) -> dict[str, int]:
    """Re-enqueue stale immutable generations; safe to run concurrently and repeatedly."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=settings.stale_analysis_minutes)
    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.analysis_generation.is_not(None),
            or_(
                (JournalEntry.analysis_state == "pending") & (JournalEntry.analysis_queued_at <= cutoff),
                (JournalEntry.analysis_state == "processing") & (JournalEntry.analysis_started_at <= cutoff),
            ),
        )
        .order_by(JournalEntry.analysis_queued_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    recovered = failed = 0
    for entry in entries:
        generation = entry.analysis_generation
        try:
            entry.analysis_job_id = enqueue_analysis_job(entry.id, generation, replace_terminal=True)
            entry.analysis_state = "pending"
            entry.analysis_queued_at = now
            entry.analysis_started_at = None
            entry.analysis_error = None
            recovered += 1
        except Exception as exc:
            entry.analysis_state = "pending"
            entry.analysis_error = "AI analysis is waiting to be queued."
            failed += 1
            logger.warning("Could not recover analysis job for entry %s (%s)", entry.id, type(exc).__name__)
    db.commit()
    return {"examined": len(entries), "recovered": recovered, "failed": failed}
