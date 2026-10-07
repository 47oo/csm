"""Declarative base and metadata naming convention (DB-D6).

F001 defines no business tables; this module exists so that migration metadata
and future models share one naming convention from the first revision.

Naming convention:
- ``ix``: ``ix_<table>_<columns>``
- ``uq``: ``uq_<table>_<columns>``
- ``ck``: ``ck_<table>_<constraint_name>`` (CheckConstraint must be named explicitly)
- ``fk``: ``fk_<table>_<column>_<referred_table>``
- ``pk``: ``pk_<table>``

Expression indexes must be given an explicit name; autogenerate does not detect
extensions or expression indexes (DB-D7).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Finalized A2: pk template is ``pk_%(table_name)s`` (without a trailing paren).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class SoftDeleteMixin:
    """Soft-delete column shared by business objects (DB-D26, DR-18).

    Only models that inherit this mixin carry ``deleted_at`` and are therefore
    subject to the Session-level default filter registered in
    ``app.core.db``. ``users`` / ``audit_logs`` must NOT inherit it.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Base(DeclarativeBase):
    """Common declarative base for all CSM ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)