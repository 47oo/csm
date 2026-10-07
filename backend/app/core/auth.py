"""Session resolution and the current-operator dependency (DR-08, DR-09).

``get_current_operator`` resolves the ``csm_session`` cookie to a live session:
it hashes the cookie value, joins ``users`` and requires the user to be ACTIVE
with a non-expired session. Any failure yields 401 AUTH_REQUIRED. On success the
operator is stored on ``request.state.operator`` for later Features (F003 audit).
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
from app.core.security import SESSION_COOKIE_NAME, hash_session_token
from app.models.session import UserSession
from app.models.user import User, UserStatus


@dataclass(frozen=True)
class Operator:
    """Authenticated caller identity passed to routes and future audit writes."""

    user_id: uuid.UUID
    username: str
    role: Role


def resolve_operator(db: Session, token: str | None) -> Operator | None:
    """Return the operator for ``token`` or ``None`` when unusable."""
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


def get_current_operator(
    request: Request,
    db: Session = Depends(get_db),
) -> Operator:
    """FastAPI dependency: resolve and return the authenticated operator."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    operator = resolve_operator(db, token)
    if operator is None:
        raise AuthRequired()
    request.state.operator = operator
    return operator