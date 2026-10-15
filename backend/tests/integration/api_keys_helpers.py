"""Shared helpers for the F017 integration tests.

Not a test module (no ``test_`` prefix): it provides a Bearer client factory, an
API-Key creation helper and a DB row lookup, reused by ``test_api_keys``.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select


@contextmanager
def bearer_client(app, plaintext: str):
    """Yield a TestClient that authenticates with a Bearer API Key."""
    client = TestClient(app)
    client.__enter__()
    client.headers.update({"Authorization": f"Bearer {plaintext}"})
    try:
        yield client
    finally:
        client.__exit__(None, None, None)


def create_key(
    admin_client,
    *,
    bound_user_id: str | None,
    label: str = "ci-runner",
    validity_days: int | None = None,
):
    """POST /api/v1/api-keys with an optional explicit ``validity_days``."""
    payload: dict = {"user_id": bound_user_id, "label": label}
    if validity_days is not None:
        payload["validity_days"] = validity_days
    return admin_client.post("/api/v1/api-keys", json=payload)


def key_row(auth_session_factory, key_id: uuid.UUID):
    """Fetch an ``api_keys`` ORM row from the real database."""
    from app.models.api_key import ApiKey

    with auth_session_factory() as session:
        return session.execute(
            select(ApiKey).where(ApiKey.id == key_id)
        ).scalars().one()