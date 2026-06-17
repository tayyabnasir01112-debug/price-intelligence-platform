from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PRICE_INTEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Price Intelligence Platform"
    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./data/price_intel.db"
    log_level: str = "INFO"
    max_http_concurrency: int = Field(default=20, ge=1, le=500)
    max_browser_contexts: int = Field(default=3, ge=1, le=50)
    task_lease_seconds: int = Field(default=300, ge=30)
    default_retry_budget: int = Field(default=3, ge=0, le=10)
    request_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    data_dir: Path = Path("data")


@lru_cache
def get_settings() -> Settings:
    return Settings()

