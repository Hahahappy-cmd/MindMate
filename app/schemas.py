from pydantic import BaseModel, ConfigDict, EmailStr, Field, constr
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal

# Password constraints: at least 8 characters
PasswordStr = constr(min_length=8, max_length=128)

# === User Schemas ===
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")

class UserCreate(UserBase):
    password: PasswordStr

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    

class UserLogin(BaseModel):
    username: str
    password: str

# === Token Schemas ===
class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str

class TokenRefresh(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    username: Optional[str] = None

# === Password Reset Schemas ===
class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    new_password: PasswordStr

class AccountDelete(BaseModel):
    password: str

# === Journal Entry Schemas ===
class JournalEntryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)

class JournalEntryCreate(JournalEntryBase):
    pass

class JournalEntryResponse(JournalEntryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    analysis_state: Literal["pending", "processing", "completed", "failed"]
    analysis_job_id: Optional[str] = None
    analysis_error: Optional[str] = None
    analysis_attempts: int = 0
    analysis_queued_at: Optional[datetime] = None
    analysis_started_at: Optional[datetime] = None
    analysis_completed_at: Optional[datetime] = None
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    sentiment_strength: Optional[float] = None
    analysis_confidence: Optional[float] = None
    analysis_method: Optional[str] = None
    analysis_version: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    subjectivity: Optional[float] = None
    word_count: Optional[int] = None
    detected_emotions: Dict[str, float] = Field(default_factory=dict)
    dominant_emotion: Optional[str] = None
    emotional_intensity: Optional[float] = None
    emotion_score_semantics: str = "unknown"
    emotion_model_name: Optional[str] = None
    emotion_model_version: Optional[str] = None
    emotion_threshold: Optional[float] = None
    emotion_chunks: Optional[int] = None
    key_phrases: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None
    user_id: int
    

class EmotionData(BaseModel):
    joy: float = 0
    sadness: float = 0
    anger: float = 0
    fear: float = 0
    surprise: float = 0
    trust: float = 0
    anticipation: float = 0
    disgust: float = 0

class JournalEntryEnhanced(JournalEntryResponse):
    pass

class JournalEntryUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)


class AnalysisStatus(BaseModel):
    entry_id: int
    state: Literal["pending", "processing", "completed", "failed"]
    job_id: Optional[str] = None
    attempts: int
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

# === User with Entries ===
class UserWithEntries(UserResponse):
    entries: List[JournalEntryResponse] = []

class WeeklySummary(BaseModel):
    summary: str
    statistics: Dict[str, Any]
    insights: List[str]
    recommendations: List[str]

class EmotionTrends(BaseModel):
    period_days: int
    total_entries: int
    trend_analysis: Dict[str, Any]
    entries: List[Dict[str, Any]]

class DashboardAnalytics(BaseModel):
    total_entries: int
    entries_this_week: int
    current_streak: int
    average_sentiment: Optional[float]
    sentiment_over_time: List[Dict[str, Any]]
    dominant_emotion_over_time: List[Dict[str, Any]]
    emotion_distribution: Dict[str, float]
    sentiment_by_weekday: List[Dict[str, Any]]


class LongTermAnalytics(BaseModel):
    period: Literal["7", "30", "90", "all"]
    period_days: Optional[int]
    status: Literal["ready", "insufficient_data"]
    minimum_entries: int
    total_entries: int
    average_sentiment: Optional[float]
    sentiment_trend: str
    rolling_sentiment: List[Dict[str, Any]]
    comparison: Dict[str, Any]
    dominant_emotions: List[Dict[str, Any]]
    emotion_distribution: Dict[str, float]
    emotion_over_time: List[Dict[str, Any]]
    sentiment_by_weekday: List[Dict[str, Any]]
    entry_frequency: List[Dict[str, Any]]
    themes: List[Dict[str, Any]]
    insights: List[str]
