from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    token_version = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    entries = relationship("JournalEntry", back_populates="owner", cascade="all, delete-orphan")
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    refresh_sessions = relationship("RefreshSession", back_populates="user", cascade="all, delete-orphan")

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    analysis_state = Column(String(16), default="pending", nullable=False, index=True)
    analysis_generation = Column(String(36), nullable=True)
    analysis_job_id = Column(String(128), nullable=True)
    analysis_error = Column(Text, nullable=True)
    analysis_attempts = Column(Integer, default=0, nullable=False)
    analysis_queued_at = Column(DateTime(timezone=True), nullable=True)
    analysis_started_at = Column(DateTime(timezone=True), nullable=True)
    analysis_completed_at = Column(DateTime(timezone=True), nullable=True)
    sentiment_score = Column(Float)
    sentiment_label = Column(String(32))
    sentiment_strength = Column(Float, nullable=True)
    analysis_confidence = Column(Float, nullable=True)
    analysis_method = Column(String(64), nullable=True)
    analysis_version = Column(String(64), nullable=True)
    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    subjectivity = Column(Float, nullable=True)  # New: How subjective/objective
    word_count = Column(Integer, nullable=True)  # New: Word count
    emotion_data = Column(JSONB, nullable=True)
    dominant_emotion = Column(String(32), nullable=True)
    emotional_intensity = Column(Float, nullable=True)
    emotion_model_name = Column(String(128), nullable=True)
    emotion_model_version = Column(String(64), nullable=True)
    emotion_score_semantics = Column(String(64), nullable=True)
    emotion_threshold = Column(Float, nullable=True)
    emotion_chunks = Column(Integer, nullable=True)
    theme_embedding = Column(JSONB, nullable=True)
    theme_embedding_model = Column(String(128), nullable=True)
    theme_embedding_version = Column(String(64), nullable=True)
    theme_embedding_hash = Column(String(64), nullable=True)
    theme_embedded_at = Column(DateTime(timezone=True), nullable=True)
    key_phrases = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    owner = relationship("User", back_populates="entries")

    __table_args__ = (
        Index("ix_journal_entries_user_created", "user_id", "created_at"),
        Index("ix_journal_entries_user_state_created", "user_id", "analysis_state", "created_at"),
        CheckConstraint("analysis_state IN ('pending','processing','completed','failed')", name="ck_journal_analysis_state"),
        CheckConstraint("analysis_attempts >= 0", name="ck_journal_analysis_attempts"),
    )

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc) + timedelta(hours=1), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    user = relationship("User", back_populates="reset_tokens")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id = Column(Integer, primary_key=True)
    jti_hash = Column(String(64), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="refresh_sessions")
    __table_args__ = (Index("ix_refresh_sessions_user_active", "user_id", "revoked_at"),)
