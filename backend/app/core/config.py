"""Application settings.

Loaded from environment variables (or a ``.env`` file when present).
Field names map case-insensitively to env vars, e.g. ``DATABASE_URL`` -> ``database_url``.

Credential boundary (requirements §22/§30): real credentials are injected via
environment / ``.env`` (not committed). Nothing here is logged or echoed.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the CSM backend.

    Pool / timeout / isolation skeleton per database design DB-D8. Timeouts are
    applied as psycopg connection options. The migration engine deliberately does
    NOT inherit these timeouts (see alembic/env.py, DB-D5).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: str = "development"
    api_port: int = 8000
    log_level: str = "INFO"
    # Display timezone configuration slot; formal time contract signed in F003/D01.
    display_timezone: str = "UTC"

    # --- F002 authentication (Contract §2, DR-08, DR-12) ---
    # Absolute session lifetime in hours (no sliding renewal).
    session_ttl_hours: int = 12
    # One-shot bootstrap credentials, injected from the environment (never committed).
    initial_admin_username: str = ""
    initial_admin_password: str = ""
    # Comma-separated extra origins accepted as same-origin for CSRF checks.
    auth_allowed_origins: str = ""

    # --- Database ---
    database_url: str = "postgresql+psycopg://csm:csm@db:5432/csm"

    # DB-D8 connection pool skeleton.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800
    db_pool_timeout: int = 30

    # DB-D8 statement / lock timeouts (milliseconds).
    db_statement_timeout_ms: int = 30000
    db_lock_timeout_ms: int = 5000

    db_application_name: str = "csm-backend"

    # F009 (Contract §1.2): cap on the ``address_in_use`` conflicts preview.
    # ``conflict_count`` always reports the full total; ``conflicts`` returns at
    # most this many descriptors and ``conflicts_truncated`` flags the cut.
    conflict_preview_limit: int = 100

    @property
    def db_connect_options(self) -> str:
        """psycopg server options string for statement/lock timeouts."""
        return (
            f"-c statement_timeout={self.db_statement_timeout_ms} "
            f"-c lock_timeout={self.db_lock_timeout_ms}"
        )

    @property
    def is_production(self) -> bool:
        """Whether the Secure cookie flag must be set (Contract §2)."""
        return self.app_env.strip().lower() == "production"

    @property
    def auth_allowed_origins_list(self) -> list[str]:
        """Parse ``AUTH_ALLOWED_ORIGINS`` (comma-separated) into a list."""
        return [item.strip() for item in self.auth_allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()