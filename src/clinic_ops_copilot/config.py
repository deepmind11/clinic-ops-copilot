"""Runtime configuration loaded from environment variables.

Single source of truth for env-driven config. Other modules should never
read os.environ directly. Use ``settings`` everywhere.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from .env or process env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    # Postgres (operational FHIR database)
    database_url: str = "postgresql://clinicops:clinicops_dev@localhost:5433/clinic_ops"

    # SQLite events store (observability)
    events_db_path: str = "events.db"

    # API server
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Logging
    log_level: str = "INFO"


settings = Settings()
