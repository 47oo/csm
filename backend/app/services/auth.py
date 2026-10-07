"""Authentication service (DR-07, DR-08, DR-14).

Business rules (normalisation, credential verification, session lifetime) live
here; routes only translate HTTP. Credential failures are always indistinct
(unknown account, wrong password or disabled account) and yield the same 401.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import InvalidCredentials
from app.core.security import (
    generate_session_token,
    hash_session_token,
    verify_password,
    verify_unknown_user,
)
from app.models.session import UserSession
from app.models.user import User, UserStatus

# DR-14: lowercase, 3-64 chars from [a-z0-9._-].
USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,64}$")


def normalize_username(username: str) -> str:
    """Normalise a login identifier: trim surrounding whitespace, lowercase."""
    return username.strip().lower()


def is_valid_username(normalized: str) -> bool:
    """Whether an already-normalised username matches the DR-14 format."""
    return bool(USERNAME_PATTERN.fullmatch(normalized))


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Return the ACTIVE user for valid credentials, else ``None``.

    Verification runs for unknown/disabled accounts too (dummy hash / real hash)
    so the response time does not reveal account existence.
    """
    normalized = normalize_username(username)
    user = (
        db.execute(select(User).where(User.username == normalized)).scalars().first()
    )
    if user is None:
        verify_unknown_user(password)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if user.status != UserStatus.ACTIVE.value:
        return None
    return user


def create_session(db: Session, user: User) -> tuple[str, datetime]:
    """Create a persisted session; returns the clear token and absolute expiry."""
    settings = get_settings()
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
    )
    db.commit()
    return token, expires_at


def delete_session(db: Session, token: str) -> None:
    """Delete the session row matching ``token`` (idempotent)."""
    db.execute(
        delete(UserSession).where(
            UserSession.token_hash == hash_session_token(token)
        )
    )
    db.commit()


def login(db: Session, username: str, password: str) -> tuple[User, str, datetime]:
    """Authenticate and start a session; raises InvalidCredentials on failure."""
    user = authenticate(db, username, password)
    if user is None:
        raise InvalidCredentials()
    token, expires_at = create_session(db, user)
    return user, token, expires_at


def logout(db: Session, token: str) -> None:
    """End the session identified by ``token``."""
    delete_session(db, token)