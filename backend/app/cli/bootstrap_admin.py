"""One-shot bootstrap CLI for the initial ADMIN (DR-12).

Invoked as ``python -m app.cli.bootstrap_admin`` (Compose one-shot service
``bootstrap``) or called directly as ``run(settings=..., session_factory=...)``
by tests.

Exit codes:
- ``0``: admin created, or idempotent no-op (users already exist / concurrent win);
- ``2``: users table empty but ``INITIAL_ADMIN_USERNAME`` / ``INITIAL_ADMIN_PASSWORD``
  missing, blank or invalid (message on stderr, nothing written);
- ``1``: any other error.

The migration never writes business data; this CLI never hard-codes credentials
and never logs the password.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.permissions import Role
from app.core.security import hash_password
from app.models.user import User, UserStatus
from app.services.auth import is_valid_username, normalize_username

USAGE = "python -m app.cli.bootstrap_admin"


def run(
    settings: Settings | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    """Create the first ADMIN once, idempotently. Returns a process exit code."""
    settings = settings or get_settings()
    factory = session_factory or SessionLocal
    session = factory()
    try:
        # Idempotency is checked BEFORE credential validation: any existing user
        # (including DISABLED) makes this a no-op.
        user_count = session.execute(select(func.count()).select_from(User)).scalar_one()
        if user_count > 0:
            print("bootstrap: users already exist; nothing to do")
            return 0

        username = (settings.initial_admin_username or "").strip()
        password = settings.initial_admin_password or ""
        if not username or not password.strip():
            print(
                "bootstrap: INITIAL_ADMIN_USERNAME/INITIAL_ADMIN_PASSWORD missing or "
                "blank; refusing to create an admin (nothing written)",
                file=sys.stderr,
            )
            return 2

        normalized = normalize_username(username)
        if not is_valid_username(normalized):
            print(
                "bootstrap: INITIAL_ADMIN_USERNAME does not match the required "
                "format (3-64 of [a-z0-9._-]); nothing written",
                file=sys.stderr,
            )
            return 2

        session.add(
            User(
                username=normalized,
                password_hash=hash_password(password),
                role=Role.ADMIN.value,
                status=UserStatus.ACTIVE.value,
                version=1,
            )
        )
        session.commit()
        print(f"bootstrap: created initial admin {normalized!r}")
        return 0
    except IntegrityError:
        # Concurrent bootstrap lost the race on uq_users_username -> converge no-op.
        session.rollback()
        remaining = session.execute(select(func.count()).select_from(User)).scalar_one()
        if remaining > 0:
            print("bootstrap: a user already exists (concurrent bootstrap); nothing to do")
            return 0
        print("bootstrap: integrity error while creating the admin", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - map any failure to exit code 1
        session.rollback()
        print(f"bootstrap: failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    finally:
        session.close()


def main() -> int:
    """CLI entry point returning the exit code."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())