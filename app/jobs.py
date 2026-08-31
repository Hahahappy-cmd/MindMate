from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from rq import get_current_job

from .database import SessionLocal
from .models import JournalEntry
from .nlp.theme_model import content_hash, get_theme_embedder
from .services.analysis import analyze_entry

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def analyze_journal_entry(entry_id: int, generation: str) -> str:
    """Analyze one immutable entry generation; stale/repeated jobs are harmless."""
    db = SessionLocal()
    try:
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if not entry or entry.analysis_generation != generation:
            return "stale"
        if entry.analysis_state == "completed":
            return "already_completed"

        entry.analysis_state = "processing"
        entry.analysis_started_at = _now()
        entry.analysis_error = None
        entry.analysis_attempts = (entry.analysis_attempts or 0) + 1
        title, content = entry.title, entry.content
        db.commit()

        result = analyze_entry(content)
        embedder = get_theme_embedder()
        source = f"{title}\n\n{content}"
        embedding = embedder.embed(source)

        db.expire_all()
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if not entry or entry.analysis_generation != generation:
            return "stale"

        entry.sentiment_score = result["sentiment_score"]
        entry.sentiment_label = result["sentiment_label"]
        entry.sentiment_strength = result.get("sentiment_strength")
        entry.analysis_confidence = result.get("analysis_confidence")
        entry.analysis_method = result.get("analysis_method")
        entry.analysis_version = result.get("analysis_version")
        entry.analyzed_at = result.get("analyzed_at")
        entry.subjectivity = result.get("subjectivity")
        entry.word_count = result.get("word_count")
        entry.emotion_data = json.dumps(result.get("emotions", {}))
        entry.dominant_emotion = result.get("dominant_emotion")
        entry.emotional_intensity = result.get("emotional_intensity")
        entry.emotion_model_name = result.get("emotion_model_name")
        entry.emotion_model_version = result.get("emotion_model_version")
        entry.emotion_score_semantics = result.get("emotion_score_semantics")
        entry.emotion_threshold = result.get("emotion_threshold")
        entry.emotion_chunks = result.get("emotion_chunks")
        entry.key_phrases = json.dumps(result.get("key_phrases", []))
        entry.theme_embedding = json.dumps(embedding)
        entry.theme_embedding_hash = content_hash(source)
        entry.theme_embedding_model = embedder.model_name
        entry.theme_embedding_version = embedder.model_version
        entry.theme_embedded_at = _now()
        entry.analysis_state = "completed"
        entry.analysis_completed_at = _now()
        entry.analysis_error = None
        db.commit()
        return "completed"
    except Exception as exc:
        db.rollback()
        entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
        if entry and entry.analysis_generation == generation:
            current_job = get_current_job()
            will_retry = bool(current_job and (current_job.retries_left or 0) > 0)
            entry.analysis_state = "pending" if will_retry else "failed"
            entry.analysis_error = (
                f"AI analysis attempt failed ({type(exc).__name__}); retry scheduled."
                if will_retry
                else f"AI analysis failed ({type(exc).__name__})."
            )
            db.commit()
        logger.exception("AI analysis failed for entry %s", entry_id)
        raise
    finally:
        db.close()
