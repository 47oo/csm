"""Credential / session-token primitives (DR-07, DR-08).

- Passwords are hashed with argon2id (``argon2-cffi`` library defaults). The PHC
  string embeds its parameters and can be upgraded in place later.
- Session tokens are opaque random strings; the database only stores their
  SHA-256 hex digest, so a database leak does not expose usable tokens.
"""

from __future__ import annotations

import hashlib
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Contract §2: cookie name and token length.
SESSION_COOKIE_NAME = "csm_session"
SESSION_TOKEN_BYTES = 32  # secrets.token_urlsafe(32) -> 43 chars

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an argon2id PHC string for ``password``."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish verification; returns False on any verification error."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A throwaway PHC string used to equalise login timing for unknown users."""
    return _hasher.hash(secrets.token_urlsafe(16))


def verify_unknown_user(password: str) -> bool:
    """Perform a dummy verification so unknown-account logins take similar time."""
    verify_password(password, _dummy_hash())
    return False


def generate_session_token() -> str:
    """Return a new opaque session token (never persisted in clear)."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Return the 64-char lowercase hex SHA-256 digest stored in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()