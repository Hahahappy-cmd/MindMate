from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    jwt_secret_key: str = "mindmate-development-access-secret-change-me"
    refresh_jwt_secret_key: str = "mindmate-development-refresh-secret-change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cookie_secure: bool = False
    emotion_model_name: str = "SamLowe/roberta-base-go_emotions"
    emotion_model_revision: str = "1895400d2daef02be65e8f3c24559e0aa09d5d25"
    emotion_threshold: float = 0.5
    emotion_top_n: int = 5
    emotion_max_tokens: int = 512
    emotion_chunk_overlap: int = 64
    theme_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    theme_model_revision: str = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
    theme_similarity_threshold: float = 0.62
    theme_max_tokens: int = 256
    theme_chunk_overlap: int = 32
    redis_url: str = "redis://localhost:6379/0"
    ai_queue_name: str = "mindmate-ai"
    ai_job_timeout_seconds: int = 600
    ai_job_max_retries: int = 3

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def validate_production(self) -> None:
        if self.environment.lower() == "production":
            if "development" in self.jwt_secret_key or "development" in self.refresh_jwt_secret_key:
                raise RuntimeError("Production JWT secrets must be configured")
            if not self.cookie_secure:
                raise RuntimeError("COOKIE_SECURE must be enabled in production")


@lru_cache
def get_settings() -> Settings:
    value = Settings()
    value.validate_production()
    return value


settings = get_settings()
