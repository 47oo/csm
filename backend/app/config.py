"""运行期配置。全部经环境变量注入（ADR-004），不硬编码凭据。"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_ttl_seconds: int
    cookie_name: str
    cookie_secure: bool
    initial_admin_password: str | None


def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "CSM_DATABASE_URL",
            "postgresql+psycopg://csm:csm@localhost:5432/csm",
        ),
        session_ttl_seconds=_int_env("CSM_SESSION_TTL_SECONDS", 12 * 3600),
        cookie_name=os.environ.get("CSM_SESSION_COOKIE", "csm_session"),
        # ADR-004：仅 HTTP，不启用 Secure。
        cookie_secure=_bool_env("CSM_COOKIE_SECURE", False),
        initial_admin_password=os.environ.get("CSM_INITIAL_ADMIN_PASSWORD"),
    )


settings = get_settings()