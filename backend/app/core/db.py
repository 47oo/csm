"""Database engine / session management (DB-D8, DB-D9).

Synchronous SQLAlchemy 2.x + psycopg 3. ``def`` routes run in FastAPI's thread
pool. No async ORM, no connection-pool middleware.

``get_db()`` yields a Session and does NOT commit; commit/rollback ownership
belongs to the Service layer (requirements §24).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from app.core.config import get_settings
from app.models.base import SoftDeleteMixin

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


# --- Soft-delete default filter (DB-D26, DR-18) ----------------------------
#
# Registered on the SQLAlchemy ``Session`` base class so it also applies to
# sessions constructed outside ``SessionLocal`` (tests, CLI, future features).
# The filter only targets models inheriting ``SoftDeleteMixin`` (``users`` /
# ``audit_logs`` have no ``deleted_at`` and are untouched). Callers bypass it
# explicitly with ``execution_options={"include_deleted": True}``.


def _soft_delete_filter(orm_execute_state) -> None:
    if not orm_execute_state.is_select:
        return
    if orm_execute_state.execution_options.get("include_deleted", False):
        return
    orm_execute_state.statement = orm_execute_state.statement.options(
        with_loader_criteria(
            SoftDeleteMixin,
            lambda cls: cls.deleted_at.is_(None),
            include_aliases=True,
        )
    )


event.listens_for(Session, "do_orm_execute")(_soft_delete_filter)