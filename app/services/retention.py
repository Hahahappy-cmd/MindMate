from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models import PasswordResetToken, RefreshSession


def cleanup_expired_security_records(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    refresh_cutoff = now - timedelta(days=settings.refresh_session_retention_days)
    reset_cutoff = now - timedelta(days=settings.reset_token_retention_days)
    refresh_deleted = db.query(RefreshSession).filter(
        RefreshSession.expires_at < refresh_cutoff,
    ).delete(synchronize_session=False)
    reset_deleted = db.query(PasswordResetToken).filter(
        PasswordResetToken.expires_at < reset_cutoff,
    ).delete(synchronize_session=False)
    db.commit()
    return {"refresh_sessions_deleted": refresh_deleted, "reset_tokens_deleted": reset_deleted}
