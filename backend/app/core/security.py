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

# F017/DR-302: API Key credential prefix and token length (256-bit entropy).
API_KEY_PREFIX = "csm_ak_"
API_KEY_TOKEN_BYTES = 32

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


def generate_api_key() -> str:
    """Return a new API Key plaintext: ``csm_ak_`` + token_urlsafe(32).

    The plaintext is returned to the caller exactly once (201 response); only its
    SHA-256 hex digest is persisted (DR-309).
    """
    return API_KEY_PREFIX + secrets.token_urlsafe(API_KEY_TOKEN_BYTES)


def hash_api_key(token: str) -> str:
    """Return the 64-char lowercase hex SHA-256 digest used for lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_bearer_authorization(authorization: str | None) -> tuple[bool, str | None]:
    """Split an ``Authorization`` header into ``(bearer_present, token)``.

    ``bearer_present`` is True when the header scheme is ``Bearer``
    (case-insensitive), even if the token is empty — such a request takes the
    API Key path and yields 401 rather than falling back to the Cookie. A
    non-Bearer scheme (e.g. ``Basic``) or a missing header is ignored by both the
    auth resolver and the CSRF guard (Contract §1, DR-302/DR-303).
    """
    if not authorization:
        return False, None
    parts = authorization.split(None, 1)
    if parts and parts[0].lower() == "bearer":
        token = parts[1].strip() if len(parts) > 1 else ""
        return True, token or None
    return False, None