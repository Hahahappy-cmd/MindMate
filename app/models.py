from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    entries = relationship("JournalEntry", back_populates="owner", cascade="all, delete-orphan")
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), index=True, nullable=False)
    content = Column(Text, nullable=False)
    sentiment_score = Column(Float)
    sentiment_label = Column(String)
    sentiment_strength = Column(Float, nullable=True)
    analysis_confidence = Column(Float, nullable=True)
    analysis_method = Column(String(64), nullable=True)
    analysis_version = Column(String(32), nullable=True)
    analyzed_at = Column(DateTime, nullable=True)
    subjectivity = Column(Float, nullable=True)  # New: How subjective/objective
    word_count = Column(Integer, nullable=True)  # New: Word count
    emotion_data = Column(Text, nullable=True)   # New: JSON string of emotions
    dominant_emotion = Column(String(32), nullable=True)
    emotional_intensity = Column(Float, nullable=True)
    key_phrases = Column(Text, nullable=True)    # New: JSON string of key phrases
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    owner = relationship("User", back_populates="entries")

    __table_args__ = (
        Index("ix_journal_entries_user_created", "user_id", "created_at"),
    )

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime, default=lambda: datetime.now(timezone.utc) + timedelta(hours=1), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    user = relationship("User", back_populates="reset_tokens")
