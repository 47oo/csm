"""User / account management service (Contract §4, DR-218/DR-219/DR-220).

Business rules live here: username normalisation/format, password hashing,
uniqueness, optimistic-lock PATCH and same-transaction session invalidation on
disable. Account events are audited with ``object_type="user"`` and a whitelist
snapshot ``{username, role, status}`` — password material never reaches the
audit trail. There is no physical delete, no self-registration and no password
change/reset.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from app.core.auth import Operator
from app.core.permissions import Role
from app.core.security import hash_password
from app.models.session import UserSession
from app.models.user import User, UserStatus
from app.services import audit
from app.services.auth import is_valid_username, normalize_username

OBJECT_TYPE = "user"
SORT_FIELDS = ("username", "role", "status", "created_at", "updated_at")
ORDERS = ("asc", "desc")
VALID_ROLES = tuple(role.value for role in Role)
VALID_STATUSES = tuple(status.value for status in UserStatus)

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

_SORT_COLUMNS = {
    "username": User.username,
    "role": User.role,
    "status": User.status,
    "created_at": User.created_at,
    "updated_at": User.updated_at,
}


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def user_snapshot(user: User) -> dict[str, Any]:
    """Whitelisted account snapshot handed to :mod:`app.services.audit`."""
    return {
        "username": user.username,
        "role": user.role,
        "status": user.status,
    }


def _validate_password(password: Any) -> str:
    if not isinstance(password, str) or not password:
        raise _field_error("password", "password is required")
    if not (PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH):
        raise _field_error(
            "password",
            f"password must be between {PASSWORD_MIN_LENGTH} and "
            f"{PASSWORD_MAX_LENGTH} characters",
        )
    return password


def _validate_role(role: Any) -> str:
    if role not in VALID_ROLES:
        raise _field_error("role", "role must be VIEWER, EDITOR or ADMIN")
    return role


def _validate_status(status: Any) -> str:
    if status not in VALID_STATUSES:
        raise _field_error("status", "status must be ACTIVE or DISABLED")
    return status


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None) or ""
    if "uq_users_username" in constraint or "uq_users_username" in str(exc):
        return Conflict.unique_conflict("username")
    return ValidationError(message="user write rejected by a database constraint")


# --- reads ------------------------------------------------------------------


def list_users(
    db: Session,
    *,
    role: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[User], int]:
    """Return the filtered page of accounts plus the filtered total."""
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if role is not None:
        _validate_role(role)
    if status is not None:
        _validate_status(status)

    normalized_q: str | None = None
    if q is not None:
        normalized_q = q.strip()
        if not normalized_q:
            raise _field_error("q", "q must not be blank")
        if len(normalized_q) > 64:
            raise _field_error("q", "q must be at most 64 characters")

    filters = []
    if role is not None:
        filters.append(User.role == role)
    if status is not None:
        filters.append(User.status == status)
    if normalized_q is not None:
        filters.append(
            User.username.ilike(f"%{_escape_like(normalized_q)}%", escape="\\")
        )

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    statement = (
        select(User)
        .where(*filters)
        .order_by(ordered, User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = select(func.count()).select_from(User).where(*filters)

    items = list(db.execute(statement).scalars().all())
    total = int(db.execute(total_statement).scalar_one())
    return items, total


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    """Return an account by id (``users`` has no soft delete)."""
    return db.execute(select(User).where(User.id == user_id)).scalars().first()


# --- writes -----------------------------------------------------------------


def create_user(
    db: Session,
    operator: Operator | None,
    *,
    username: str,
    password: str,
    role: str,
) -> User:
    """Create an account and write a CREATE audit row in the same transaction."""
    normalized = normalize_username(username)
    if not is_valid_username(normalized):
        raise _field_error(
            "username",
            "username must be 3-64 characters from [a-z0-9._-]",
        )
    validated_role = _validate_role(role)
    validated_password = _validate_password(password)

    existing = db.execute(
        select(User.id).where(User.username == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict.unique_conflict("username")

    user = User(
        username=normalized,
        password_hash=hash_password(validated_password),
        role=validated_role,
        status=UserStatus.ACTIVE.value,
        version=1,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _translate_integrity_error(exc) from exc

    audit.record(
        db,
        operator,
        action="CREATE",
        object_type=OBJECT_TYPE,
        object_id=user.id,
        before=None,
        after=user_snapshot(user),
    )
    db.commit()
    return user


def update_user(
    db: Session,
    operator: Operator | None,
    user_id: uuid.UUID,
    *,
    expected_version: int,
    role: str | None = None,
    status: str | None = None,
) -> User:
    """Update role/status with optimistic locking; disable drops sessions."""
    if role is None and status is None:
        raise _field_error("role", "at least one of role or status is required")

    user = get_user(db, user_id)
    if user is None:
        raise NotFound()
    if user.version != expected_version:
        raise VersionConflict(user.version)

    values: dict[str, Any] = {}
    if role is not None:
        values["role"] = _validate_role(role)
    if status is not None:
        values["status"] = _validate_status(status)

    before = user_snapshot(user)
    values["version"] = User.version + 1
    values["updated_at"] = func.now()

    result = db.execute(
        update(User)
        .where(User.id == user_id, User.version == expected_version)
        .values(**values)
    )
    if result.rowcount == 0:
        _raise_update_conflict(db, user_id)

    if values.get("status") == UserStatus.DISABLED.value:
        db.execute(delete(UserSession).where(UserSession.user_id == user_id))

    db.flush()
    db.refresh(user)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=user.id,
        before=before,
        after=user_snapshot(user),
    )
    db.commit()
    return user


def _raise_update_conflict(db: Session, user_id: uuid.UUID) -> None:
    current_version = db.execute(
        select(User.version).where(User.id == user_id)
    ).scalar_one_or_none()
    if current_version is None:
        raise NotFound()
    raise VersionConflict(int(current_version))