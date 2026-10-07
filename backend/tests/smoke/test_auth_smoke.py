"""F002 pure-logic smoke tests (no database).

These are never evidence for PostgreSQL constraints, migrations or the real
permission dependency; they only check importable wiring and pure logic.
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.smoke


def test_role_permission_matrix_matches_section_23():
    from app.core.permissions import ROLE_PERMISSIONS, Permission, Role, permissions_for

    assert ROLE_PERMISSIONS[Role.VIEWER] == frozenset(
        {Permission.READ, Permission.VIEW_ACTIVITY}
    )
    assert ROLE_PERMISSIONS[Role.EDITOR] == frozenset(
        {Permission.READ, Permission.VIEW_ACTIVITY, Permission.WRITE, Permission.IMPORT}
    )
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)
    # Sorted, capability-only output.
    assert permissions_for(Role.ADMIN) == sorted(p.value for p in Permission)


def test_security_hash_verify_and_token_hash():
    from app.core.security import (
        generate_session_token,
        hash_password,
        hash_session_token,
        verify_password,
    )

    digest = hash_password("correct horse battery staple")
    assert digest.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", digest)
    assert not verify_password("wrong", digest)

    token = generate_session_token()
    assert len(token) >= 40
    assert len(hash_session_token(token)) == 64
    assert hash_session_token(token) != token


def test_error_envelope_shapes():
    from app.core.errors import (
        AuthRequired,
        Forbidden,
        InvalidCredentials,
        NotFound,
        VersionConflict,
    )

    assert AuthRequired().envelope()["error"] == {
        "code": "AUTH_REQUIRED",
        "message": "Authentication required",
        "details": {},
    }
    assert InvalidCredentials().status_code == 401
    assert Forbidden(reason="csrf").envelope()["error"]["details"] == {"reason": "csrf"}
    assert NotFound().status_code == 404
    assert VersionConflict(3).envelope()["error"]["details"] == {"current_version": 3}


def test_redaction_filter_masks_sensitive_keys():
    from app.core.logging import SensitiveDataFilter

    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login %(username)s %(password)s",
        args={"username": "admin", "password": "secret"},
        exc_info=None,
    )
    assert SensitiveDataFilter().filter(record)
    assert record.args["password"] == "***"
    assert record.args["username"] == "admin"


def test_settings_f002_fields(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "http://a.example, http://b.example")
    monkeypatch.setenv("SESSION_TTL_HOURS", "12")
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings(_env_file=None)
    assert settings.session_ttl_hours == 12
    assert settings.auth_allowed_origins_list == [
        "http://a.example",
        "http://b.example",
    ]
    assert settings.is_production


def test_auth_routes_registered():
    from app.api.v1.router import api_v1_router

    paths = {route.path for route in api_v1_router.routes}
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/me" in paths
    assert not any("register" in p or "signup" in p for p in paths)


def test_bootstrap_username_normalization():
    from app.services.auth import is_valid_username, normalize_username

    assert normalize_username(" Admin ") == "admin"
    assert is_valid_username("admin")
    assert not is_valid_username("Ad")