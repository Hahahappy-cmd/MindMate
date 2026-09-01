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
    cookie_samesite: str = "lax"
    cookie_domain: str | None = None
    database_url: str
    database_pool_size: int = 5
    database_max_overflow: int = 10
    jwt_issuer: str = "mindmate"
    jwt_audience: str = "mindmate-api"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    max_request_bytes: int = 262144
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
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("DATABASE_URL must use PostgreSQL with psycopg")
        if self.cookie_samesite.lower() not in {"lax", "strict", "none"}:
            raise RuntimeError("COOKIE_SAMESITE must be lax, strict, or none")
        if self.environment.lower() == "production":
            if "development" in self.jwt_secret_key or "development" in self.refresh_jwt_secret_key:
                raise RuntimeError("Production JWT secrets must be configured")
            if not self.cookie_secure:
                raise RuntimeError("COOKIE_SECURE must be enabled in production")
            if len(self.jwt_secret_key) < 32 or len(self.refresh_jwt_secret_key) < 32:
                raise RuntimeError("Production JWT secrets must be at least 32 characters")
            if self.jwt_secret_key == self.refresh_jwt_secret_key:
                raise RuntimeError("Access and refresh JWT secrets must be independent")
            if any(host in {"localhost", "127.0.0.1", "testserver"} for host in self.trusted_hosts.split(",")):
                raise RuntimeError("Production TRUSTED_HOSTS must be configured explicitly")


@lru_cache
def get_settings() -> Settings:
    value = Settings()
    value.validate_production()
    return value


settings = get_settings()
