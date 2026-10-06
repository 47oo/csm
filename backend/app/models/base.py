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

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Finalized A2: pk template is ``pk_%(table_name)s`` (without a trailing paren).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Common declarative base for all CSM ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)