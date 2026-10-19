"""API Key business service (Contract §4, DR-301..DR-318).

Business rules live here: label validation, account eligibility, DB-derived
expiry, key generation/hashing, list filtering/sorting/pagination, revocation and
the same-transaction audit write. Routes only translate HTTP. The plaintext is
returned exactly once by ``create_api_key`` and is never persisted or logged.

API Keys are not §21 business objects: revocation is modelled by ``revoked_at``
and there is no delete/restore/update path (DR-305/DR-313/DR-318).
"""

from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, aliased

from app.core.auth import Operator
from app.core.errors import Conflict, NotFound, ValidationError
from app.core.security import generate_api_key, hash_api_key
from app.models.api_key import ApiKey
from app.models.user import User, UserStatus
from app.services import audit

OBJECT_TYPE = "api_key"
SORT_FIELDS = ("created_at", "expires_at", "label")
ORDERS = ("asc", "desc")
VALID_STATUSES = ("ACTIVE", "REVOKED", "EXPIRED")
LABEL_MAX_LENGTH = 255

_SORT_COLUMNS = {
    "created_at": ApiKey.created_at,
    "expires_at": ApiKey.expires_at,
    "label": ApiKey.label,
}


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validate_label(label: Any) -> str:
    """Trim, reject blank / over-long / control-character labels (DR-305)."""
    if not isinstance(label, str):
        raise _field_error("label", "label is required")
    cleaned = label.strip()
    if not cleaned:
        raise _field_error("label", "label must not be blank")
    if len(cleaned) > LABEL_MAX_LENGTH:
        raise _field_error("label", f"label must be at most {LABEL_MAX_LENGTH} characters")
    if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in cleaned):
        raise _field_error("label", "label must not contain control characters")
    return cleaned


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def api_key_snapshot(api_key: ApiKey) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit` (no key_hash)."""
    return {
        "user_id": str(api_key.user_id),
        "label": api_key.label,
        "expires_at": _iso(api_key.expires_at),
        "revoked_at": _iso(api_key.revoked_at),
    }


def _row_query():
    """Select an ``ApiKey`` plus its bound and creator usernames."""
    bound = aliased(User)
    creator = aliased(User)
    return (
        select(ApiKey, bound.username, creator.username)
        .join(bound, bound.id == ApiKey.user_id)
        .join(creator, creator.id == ApiKey.created_by)
    )


def _fetch_row(db: Session, api_key_id: uuid.UUID):
    return db.execute(_row_query().where(ApiKey.id == api_key_id)).first()


# --- reads ------------------------------------------------------------------


def list_api_keys(
    db: Session,
    *,
    user_id: uuid.UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[tuple[ApiKey, str, str]], int]:
    """Return the filtered page plus the filtered total (Contract §3)."""
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if status is not None and status not in VALID_STATUSES:
        raise _field_error("status", "status must be ACTIVE, REVOKED or EXPIRED")

    filters = []
    if user_id is not None:
        filters.append(ApiKey.user_id == user_id)
    if status == "ACTIVE":
        filters.append(ApiKey.revoked_at.is_(None))
        filters.append(ApiKey.expires_at > func.now())
    elif status == "REVOKED":
        filters.append(ApiKey.revoked_at.isnot(None))
    elif status == "EXPIRED":
        filters.append(ApiKey.revoked_at.is_(None))
        filters.append(ApiKey.expires_at <= func.now())

    if q is not None:
        if not isinstance(q, str):
            raise _field_error("q", "q must be a string")
        cleaned = q.strip()
        if not cleaned:
            raise _field_error("q", "q must not be blank")
        if len(cleaned) > LABEL_MAX_LENGTH:
            raise _field_error("q", f"q must be at most {LABEL_MAX_LENGTH} characters")
        filters.append(ApiKey.label.ilike(f"%{_escape_like(cleaned)}%", escape="\\"))

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    statement = (
        _row_query()
        .where(*filters)
        .order_by(ordered, ApiKey.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(ApiKey).where(*filters)

    items = list(db.execute(statement).all())
    total = int(db.execute(total_statement).scalar_one())
    return items, total


def get_api_key(db: Session, api_key_id: uuid.UUID):
    """Return ``(ApiKey, username, created_by_username)`` or ``None``."""
    return _fetch_row(db, api_key_id)


# --- writes -----------------------------------------------------------------


def create_api_key(
    db: Session,
    operator: Operator | None,
    *,
    user_id: uuid.UUID,
    label: str,
    validity_days: int,
) -> tuple[ApiKey, str, str, str]:
    """Create a key and write a CREATE audit row in the same transaction.

    Returns ``(api_key, username, created_by_username, plaintext)``. The
    ``expires_at`` is derived from the database transaction ``now()`` so the
    365-day boundary is exact and matches ``created_at`` (DR-308/DB-D307).
    """
    cleaned_label = _validate_label(label)

    user = db.execute(select(User).where(User.id == user_id)).scalars().first()
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise _field_error("user_id", "user_id must reference an ACTIVE account")

    # Same transaction timestamp as the ``created_at`` server default.
    db_now = db.execute(select(func.now())).scalar_one()
    expires_at = db_now + timedelta(days=validity_days)

    plaintext = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        label=cleaned_label,
        key_hash=hash_api_key(plaintext),
        created_by=operator.user_id if operator is not None else user.id,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.flush()
    db.refresh(api_key)

    audit.record(
        db,
        operator,
        action="CREATE",
        object_type=OBJECT_TYPE,
        object_id=api_key.id,
        before=None,
        after=api_key_snapshot(api_key),
    )
    db.commit()
    return api_key, user.username, (operator.username if operator else "system"), plaintext


def revoke_api_key(
    db: Session,
    operator: Operator | None,
    api_key_id: uuid.UUID,
) -> tuple[ApiKey, str, str]:
    """Revoke a key (idempotent conflict on already-revoked) with audit."""
    api_key = db.get(ApiKey, api_key_id)
    if api_key is None:
        raise NotFound()
    if api_key.revoked_at is not None:
        raise Conflict("already_revoked")

    before = api_key_snapshot(api_key)
    result = db.execute(
        update(ApiKey)
        .where(ApiKey.id == api_key_id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    if result.rowcount == 0:
        # Lost a race with a concurrent revoke: it is now REVOKED.
        raise Conflict("already_revoked")

    db.refresh(api_key)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=api_key.id,
        before=before,
        after=api_key_snapshot(api_key),
    )
    db.commit()
    row = _fetch_row(db, api_key_id)
    assert row is not None
    return row