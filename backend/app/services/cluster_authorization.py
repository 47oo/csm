"""Cluster authorization business service (F026 Contract §3–§9).

Rules live here; routes only translate HTTP. Grants and revocations write their
Audit row in the same transaction. The valid-row uniqueness is enforced by the
database partial unique index, so a concurrent duplicate maps to 409 rather than
silently succeeding.
"""

from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.auth import Operator
from app.core.errors import Conflict, NotFound, ValidationError
from app.core.permissions import Role
from app.models.cluster import Cluster
from app.models.user import User
from app.models.user_cluster_authorization import UserClusterAuthorization
from app.services import audit

OBJECT_TYPE = "user_cluster_authorization"
SORT_FIELDS = ("granted_at", "revoked_at")
ORDERS = ("asc", "desc")
VALID_STATUSES = ("ACTIVE", "REVOKED")
Q_MAX_LENGTH = 64

_SORT_COLUMNS = {
    "granted_at": UserClusterAuthorization.granted_at,
    "revoked_at": UserClusterAuthorization.revoked_at,
}


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def authorization_snapshot(
    authorization: UserClusterAuthorization,
) -> dict[str, Any]:
    """Whitelisted snapshot handed to :mod:`app.services.audit`."""
    return {
        "user_id": str(authorization.user_id),
        "cluster_id": str(authorization.cluster_id),
        "granted_at": _iso(authorization.granted_at),
        "granted_by": (
            str(authorization.granted_by)
            if authorization.granted_by is not None
            else None
        ),
        "revoked_at": _iso(authorization.revoked_at),
        "revoked_by": (
            str(authorization.revoked_by)
            if authorization.revoked_by is not None
            else None
        ),
    }


def _base_query():
    grantor = aliased(User)
    revoker = aliased(User)
    return (
        select(
            UserClusterAuthorization,
            User,
            Cluster,
            grantor.username,
            revoker.username,
        )
        .join(User, User.id == UserClusterAuthorization.user_id)
        .join(Cluster, Cluster.id == UserClusterAuthorization.cluster_id)
        .outerjoin(grantor, grantor.id == UserClusterAuthorization.granted_by)
        .outerjoin(revoker, revoker.id == UserClusterAuthorization.revoked_by)
        # Authorization history must still show soft-deleted Clusters.
        .execution_options(include_deleted=True)
    )


def _fetch_row(db: Session, authorization_id: uuid.UUID):
    return db.execute(
        _base_query().where(UserClusterAuthorization.id == authorization_id)
    ).first()


def _validate_q(q: str | None) -> str | None:
    if q is None:
        return None
    if not isinstance(q, str):
        raise _field_error("q", "q must be a string")
    cleaned = q.strip()
    if not cleaned:
        raise _field_error("q", "q must not be blank")
    if len(cleaned) > Q_MAX_LENGTH:
        raise _field_error("q", f"q must be at most {Q_MAX_LENGTH} characters")
    if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in cleaned):
        raise _field_error("q", "q must not contain control characters")
    return cleaned


def list_authorizations(
    db: Session,
    *,
    user_id: uuid.UUID,
    status: str | None = None,
    cluster_id: uuid.UUID | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "granted_at",
    order: str = "desc",
) -> tuple[list[tuple], int]:
    """Return the filtered page plus the filtered total (Contract §3)."""
    # Contract §3/§5 P-1: path object first — an unknown or non-UUID account is
    # 404 before any semantic query validation, so `q` is only validated after
    # the account exists. Typed query params (status/cluster_id/page/page_size/
    # sort/order) are rejected by the route before the handler; undeclared
    # params are rejected by `_reject_unknown_query` as the handler's first
    # step, before path and semantic validation — hence 422 even for an unknown
    # account. This is not an information-leak hardening measure: the endpoint
    # is USER_ADMIN only.
    _get_user_or_404(db, user_id)
    if sort not in SORT_FIELDS:
        raise _field_error("sort", "unsupported sort field")
    if order not in ORDERS:
        raise _field_error("order", "order must be asc or desc")
    if status is not None and status not in VALID_STATUSES:
        raise _field_error("status", "status must be ACTIVE or REVOKED")
    cleaned_q = _validate_q(q)

    filters = [UserClusterAuthorization.user_id == user_id]
    if status == "ACTIVE":
        filters.append(UserClusterAuthorization.revoked_at.is_(None))
    elif status == "REVOKED":
        filters.append(UserClusterAuthorization.revoked_at.isnot(None))
    if cluster_id is not None:
        filters.append(UserClusterAuthorization.cluster_id == cluster_id)
    if cleaned_q is not None:
        pattern = f"%{_escape_like(cleaned_q)}%"
        filters.append(
            or_(
                Cluster.code.ilike(pattern, escape="\\"),
                Cluster.name.ilike(pattern, escape="\\"),
            )
        )

    sort_column = _SORT_COLUMNS[sort]
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    statement = (
        _base_query()
        .where(*filters)
        .order_by(ordered, UserClusterAuthorization.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_statement = (
        select(func.count())
        .select_from(UserClusterAuthorization)
        .join(Cluster, Cluster.id == UserClusterAuthorization.cluster_id)
        .where(*filters)
        .execution_options(include_deleted=True)
    )

    items = list(db.execute(statement).all())
    total = int(db.execute(total_statement).scalar_one())
    return items, total


def get_authorization(db: Session, authorization_id: uuid.UUID):
    return _fetch_row(db, authorization_id)


def _get_user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound()
    return user


def _get_cluster_or_422(db: Session, cluster_id: uuid.UUID) -> Cluster:
    cluster = db.execute(
        select(Cluster)
        .where(Cluster.id == cluster_id)
        .execution_options(include_deleted=True)
    ).scalars().first()
    if cluster is None or cluster.deleted_at is not None:
        raise _field_error(
            "cluster_id", "cluster_id must reference an existing, non-deleted Cluster"
        )
    return cluster


def grant_authorization(
    db: Session,
    operator: Operator,
    *,
    user_id: uuid.UUID,
    cluster_id: uuid.UUID,
):
    """Grant one Cluster to one account, with a same-transaction Audit row."""
    user = _get_user_or_404(db, user_id)
    if user.role == Role.ADMIN.value:
        raise _field_error("user_id", "target account is ADMIN")
    cluster = _get_cluster_or_422(db, cluster_id)

    authorization = UserClusterAuthorization(
        user_id=user.id,
        cluster_id=cluster.id,
        granted_by=operator.user_id,
    )
    db.add(authorization)
    try:
        db.flush()
        db.refresh(authorization)
        audit.record(
            db,
            operator,
            action="CREATE",
            object_type=OBJECT_TYPE,
            object_id=authorization.id,
            before=None,
            after=authorization_snapshot(authorization),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        diag = getattr(exc.orig, "diag", None)
        constraint = getattr(diag, "constraint_name", None)
        if constraint == "uq_user_cluster_authorizations_user_id_cluster_id":
            raise Conflict("already_granted") from exc
        # Other integrity failures are not a duplicate grant; surface them.
        raise

    row = _fetch_row(db, authorization.id)
    assert row is not None
    return row


def revoke_authorization(
    db: Session,
    operator: Operator,
    authorization_id: uuid.UUID,
):
    """Revoke one authorization; history is retained and never deleted."""
    authorization = db.get(UserClusterAuthorization, authorization_id)
    if authorization is None:
        raise NotFound()
    if authorization.revoked_at is not None:
        raise Conflict("already_revoked")

    before = authorization_snapshot(authorization)
    result = db.execute(
        update(UserClusterAuthorization)
        .where(
            UserClusterAuthorization.id == authorization_id,
            UserClusterAuthorization.revoked_at.is_(None),
        )
        .values(revoked_at=func.now(), revoked_by=operator.user_id)
    )
    if result.rowcount == 0:
        raise Conflict("already_revoked")

    db.refresh(authorization)
    audit.record(
        db,
        operator,
        action="UPDATE",
        object_type=OBJECT_TYPE,
        object_id=authorization.id,
        before=before,
        after=authorization_snapshot(authorization),
    )
    db.commit()

    row = _fetch_row(db, authorization_id)
    assert row is not None
    return row
