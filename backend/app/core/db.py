"""Database engine / session management (DB-D8, DB-D9).

Synchronous SQLAlchemy 2.x + psycopg 3. ``def`` routes run in FastAPI's thread
pool. No async ORM, no connection-pool middleware.

``get_db()`` yields a Session and does NOT commit; commit/rollback ownership
belongs to the Service layer (requirements §24).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

# Application engine. Pool parameters and server-side timeouts per DB-D8.
engine: Engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_recycle=_settings.db_pool_recycle,
    pool_timeout=_settings.db_pool_timeout,
    connect_args={
        "application_name": _settings.db_application_name,
        "options": _settings.db_connect_options,
    },
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: provide a Session, roll back on error, always close."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()