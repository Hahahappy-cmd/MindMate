from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from ..database import get_db
from .. import models, schemas
from ..AI import sentiment
from ..services.analysis import summarize_entries
from ..services.long_term_analytics import VALID_PERIODS, build_long_term_analytics
from ..queue import enqueue_analysis_job
from ..dependencies import get_current_user, require_csrf

router = APIRouter(prefix="/entries", tags=["entries"])
logger = logging.getLogger(__name__)


DERIVED_FIELDS = (
    "sentiment_score", "sentiment_label", "sentiment_strength", "analysis_confidence",
    "analysis_method", "analysis_version", "analyzed_at", "subjectivity", "word_count",
    "emotion_data", "dominant_emotion", "emotional_intensity", "emotion_model_name",
    "emotion_model_version", "emotion_score_semantics", "emotion_threshold", "emotion_chunks",
    "key_phrases", "theme_embedding", "theme_embedding_model", "theme_embedding_version",
    "theme_embedding_hash", "theme_embedded_at",
)


def prepare_analysis(entry: models.JournalEntry) -> str:
    for field in DERIVED_FIELDS:
        setattr(entry, field, None)
    generation = str(uuid.uuid4())
    entry.analysis_state = "pending"
    entry.analysis_generation = generation
    entry.analysis_job_id = None
    entry.analysis_error = None
    entry.analysis_attempts = 0
    entry.analysis_queued_at = datetime.now(timezone.utc)
    entry.analysis_started_at = None
    entry.analysis_completed_at = None
    return generation


def enqueue_or_mark_failed(entry: models.JournalEntry, generation: str, db: Session) -> None:
    try:
        entry.analysis_job_id = enqueue_analysis_job(entry.id, generation)
    except Exception as exc:
        logger.warning("Could not enqueue AI analysis for entry %s: %s", entry.id, type(exc).__name__)
        entry.analysis_state = "failed"
        entry.analysis_error = "AI analysis could not be queued. Please try editing the entry again."
    db.commit()
    db.refresh(entry)

def serialize_entry(entry: models.JournalEntry) -> dict:
    def load_json(value, fallback):
        if not value:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    return {
        "id": entry.id,
        "analysis_state": entry.analysis_state,
        "analysis_job_id": entry.analysis_job_id,
        "analysis_error": entry.analysis_error,
        "analysis_attempts": entry.analysis_attempts or 0,
        "analysis_queued_at": entry.analysis_queued_at,
        "analysis_started_at": entry.analysis_started_at,
        "analysis_completed_at": entry.analysis_completed_at,
        "title": entry.title,
        "content": entry.content,
        "sentiment_score": entry.sentiment_score,
        "sentiment_label": entry.sentiment_label,
        "sentiment_strength": entry.sentiment_strength,
        "analysis_confidence": entry.analysis_confidence,
        "analysis_method": entry.analysis_method,
        "analysis_version": entry.analysis_version,
        "analyzed_at": entry.analyzed_at,
        "subjectivity": entry.subjectivity,
        "word_count": entry.word_count,
        "detected_emotions": load_json(entry.emotion_data, {}),
        "dominant_emotion": entry.dominant_emotion,
        "emotional_intensity": entry.emotional_intensity,
        "emotion_score_semantics": entry.emotion_score_semantics or "keyword_match_density",
        "emotion_model_name": entry.emotion_model_name,
        "emotion_model_version": entry.emotion_model_version,
        "emotion_threshold": entry.emotion_threshold,
        "emotion_chunks": entry.emotion_chunks,
        "key_phrases": load_json(entry.key_phrases, []),
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "user_id": entry.user_id,
    }

# ========== CREATE ==========
@router.post("/", response_model=schemas.JournalEntryEnhanced, status_code=status.HTTP_201_CREATED)
def create_entry(
    entry: schemas.JournalEntryCreate,
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db_entry = models.JournalEntry(
        title=entry.title,
        content=entry.content,
        user_id=current_user.id
    )
    generation = prepare_analysis(db_entry)
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    enqueue_or_mark_failed(db_entry, generation, db)
    return serialize_entry(db_entry)

# ========== READ ALL ==========
@router.get("/", response_model=List[schemas.JournalEntryEnhanced])
def get_entries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Only return current user's entries
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user.id
    ).order_by(models.JournalEntry.created_at.desc()).all()
    return [serialize_entry(entry) for entry in entries]

# ========== WEEK 4 AI FEATURES ==========

@router.get("/weekly-summary", response_model=schemas.WeeklySummary)
def get_weekly_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get AI-generated weekly summary"""
    # Get entries from last week
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user.id,
        models.JournalEntry.analysis_state == "completed",
        models.JournalEntry.created_at >= one_week_ago
    ).order_by(models.JournalEntry.created_at).all()
    
    # Convert to dict format for summarizer
    entries_data = []
    for entry in entries:
        entry_dict = {
            "id": entry.id,
            "title": entry.title,
            "content": entry.content,
            "sentiment_score": entry.sentiment_score,
            "sentiment_label": entry.sentiment_label,
            "subjectivity": entry.subjectivity,
            "word_count": entry.word_count,
            "emotion_data": entry.emotion_data,
            "created_at": entry.created_at.isoformat() if entry.created_at else None
        }
        entries_data.append(entry_dict)
    
    # Generate summary
    summary = summarize_entries(entries_data)
    
    return summary

@router.get("/emotion-trends", response_model=schemas.EmotionTrends)
def get_emotion_trends(
    days: int = 30,  # Default to 30 days
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get emotion trends over time"""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user.id,
        models.JournalEntry.analysis_state == "completed",
        models.JournalEntry.created_at >= start_date
    ).order_by(models.JournalEntry.created_at).all()
    
    # Prepare data for trend analysis
    entries_data = []
    for entry in entries:
        emotions = {}
        if entry.emotion_data:
            try:
                emotions = entry.emotion_data if isinstance(entry.emotion_data, dict) else json.loads(entry.emotion_data)
            except (TypeError, json.JSONDecodeError):
                pass
        
        entry_dict = {
            "sentiment_score": entry.sentiment_score,
            "sentiment_label": entry.sentiment_label,
            "emotions": emotions,
            "created_at": entry.created_at
        }
        entries_data.append(entry_dict)
    
    # Analyze trends
    trends = sentiment.analyze_emotion_trends(entries_data)
    
    return {
        "period_days": days,
        "total_entries": len(entries),
        "trend_analysis": trends,
        "entries": [
            {
                "date": e.created_at.isoformat() if e.created_at else None,
                "sentiment": e.sentiment_score,
                "label": e.sentiment_label
            }
            for e in entries[-10:]  # Last 10 entries for chart
        ]
    }

@router.get("/dashboard", response_model=schemas.DashboardAnalytics)
def get_dashboard_analytics(
    days: int = 90,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    days = max(7, min(days, 365))
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user.id,
        models.JournalEntry.analysis_state == "completed",
        models.JournalEntry.created_at >= start_date,
    ).order_by(models.JournalEntry.created_at).all()

    sentiment_entries = [e for e in entries if e.sentiment_score is not None]
    emotions = {}
    weekday_values = {i: [] for i in range(7)}
    active_dates = set()
    for entry in entries:
        if entry.created_at:
            active_dates.add(entry.created_at.date())
            if entry.sentiment_score is not None:
                weekday_values[entry.created_at.weekday()].append(entry.sentiment_score)
        if entry.emotion_data:
            try:
                data = entry.emotion_data if isinstance(entry.emotion_data, dict) else json.loads(entry.emotion_data)
                for name, score in data.items():
                    emotions[name] = emotions.get(name, 0) + score
            except (TypeError, json.JSONDecodeError):
                pass

    today = datetime.now(timezone.utc).date()
    streak = 0
    while today - timedelta(days=streak) in active_dates:
        streak += 1
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {
        "total_entries": len(entries),
        "entries_this_week": sum(1 for e in entries if e.created_at and e.created_at >= week_start),
        "current_streak": streak,
        "average_sentiment": round(sum(e.sentiment_score for e in sentiment_entries) / len(sentiment_entries), 3) if sentiment_entries else None,
        "sentiment_over_time": [{"date": e.created_at.isoformat(), "score": e.sentiment_score, "label": e.sentiment_label} for e in sentiment_entries],
        "dominant_emotion_over_time": [{"date": e.created_at.isoformat(), "emotion": e.dominant_emotion, "intensity": e.emotional_intensity} for e in entries if e.dominant_emotion],
        "emotion_distribution": {name: round(score, 3) for name, score in emotions.items()},
        "sentiment_by_weekday": [{"weekday": weekdays[i], "average": round(sum(values) / len(values), 3) if values else None} for i, values in weekday_values.items()],
    }


@router.get("/long-term-analytics", response_model=schemas.LongTermAnalytics)
def get_long_term_analytics(
    period: str = "30",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=422, detail="period must be one of: 7, 30, 90, all")
    entries = db.query(models.JournalEntry).filter(
        models.JournalEntry.user_id == current_user.id,
        models.JournalEntry.analysis_state == "completed",
    ).order_by(models.JournalEntry.created_at).all()
    return build_long_term_analytics(entries, period)


@router.get("/{entry_id}/analysis-status", response_model=schemas.AnalysisStatus)
def get_analysis_status(entry_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = db.query(models.JournalEntry).filter(
        models.JournalEntry.id == entry_id,
        models.JournalEntry.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {
        "entry_id": entry.id,
        "state": entry.analysis_state,
        "job_id": entry.analysis_job_id,
        "attempts": entry.analysis_attempts or 0,
        "queued_at": entry.analysis_queued_at,
        "started_at": entry.analysis_started_at,
        "completed_at": entry.analysis_completed_at,
        "error": entry.analysis_error,
    }

# Dynamic routes must remain after named routes so names are not parsed as IDs.
@router.get("/{entry_id}", response_model=schemas.JournalEntryEnhanced)
def get_entry(entry_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id, models.JournalEntry.user_id == current_user.id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return serialize_entry(entry)

@router.put("/{entry_id}", response_model=schemas.JournalEntryEnhanced)
def update_entry(entry_id: int, entry_update: schemas.JournalEntryUpdate, _csrf: None = Depends(require_csrf), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id, models.JournalEntry.user_id == current_user.id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    updates = entry_update.model_dump(exclude_unset=True)
    for field in ("title", "content"):
        if field in updates:
            setattr(entry, field, updates[field])
    generation = prepare_analysis(entry)
    db.commit()
    db.refresh(entry)
    enqueue_or_mark_failed(entry, generation, db)
    return serialize_entry(entry)

@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, _csrf: None = Depends(require_csrf), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id, models.JournalEntry.user_id == current_user.id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return None
