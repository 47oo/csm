"""Session / API Key resolution and the current-operator dependency.

``get_current_operator`` is the single authentication seam for every protected
endpoint. It resolves one of two credential carriers:

* ``Authorization: Bearer csm_ak_<token>`` -> API Key path (F017, DR-301/DR-302);
  a valid Bearer takes priority and the Cookie is ignored.
* otherwise the ``csm_session`` cookie -> session path (F002).

Any missing/malformed/unusable credential yields 401 AUTH_REQUIRED. On success
the operator is stored on ``request.state.operator`` for later Features (audit).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AuthRequired
from app.core.permissions import Role
from app.core.security import (
    SESSION_COOKIE_NAME,
    hash_api_key,
    hash_session_token,
    parse_bearer_authorization,
)
from app.models.api_key import ApiKey
from app.models.session import UserSession
from app.models.user import User, UserStatus


@dataclass(frozen=True)
class Operator:
    """Authenticated caller identity passed to routes and audit writes."""

    user_id: uuid.UUID
    username: str
    role: Role
    # F017/DR-315: the API Key label when authenticated via Bearer; None for
    # Cookie authentication and system paths.
    api_key_label: str | None = None


def resolve_operator(db: Session, token: str | None) -> Operator | None:
    """Return the operator for a session ``token`` or ``None`` when unusable."""
    if not token:
        return None
    statement = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.expires_at > func.now(),
            User.status == UserStatus.ACTIVE.value,
        )
    )
    user = db.execute(statement).scalars().first()
    if user is None:
        return None
    return Operator(user_id=user.id, username=user.username, role=Role(user.role))


def resolve_operator_from_api_key(db: Session, token: str | None) -> Operator | None:
    """Return the operator for an API Key ``token``, else ``None``.

    Looks up the SHA-256 digest and requires an un-revoked, un-expired key whose
    bound account is ACTIVE. Failure is indistinguishable from any other bad
    credential (DR-304); the key label is carried on the operator (DR-315).
    """
    if not token:
        return None
    statement = (
        select(ApiKey, User)
        .join(User, User.id == ApiKey.user_id)
        .where(
            ApiKey.key_hash == hash_api_key(token),
            ApiKey.revoked_at.is_(None),
            ApiKey.expires_at > func.now(),
            User.status == UserStatus.ACTIVE.value,
        )
    )
    row = db.execute(statement).first()
    if row is None:
        return None
    api_key, user = row
    return Operator(
        user_id=user.id,
        username=user.username,
        role=Role(user.role),
        api_key_label=api_key.label,
    )


def get_current_operator(
    request: Request,
    db: Session = Depends(get_db),
) -> Operator:
    """FastAPI dependency: resolve and return the authenticated operator."""
    bearer_present, bearer_token = parse_bearer_authorization(
        request.headers.get("authorization")
    )
    if bearer_present:
        operator = resolve_operator_from_api_key(db, bearer_token)
    else:
        operator = resolve_operator(db, request.cookies.get(SESSION_COOKIE_NAME))
    if operator is None:
        raise AuthRequired()
    request.state.operator = operator
    return operator