"""Log redaction (Contract §1.2, architecture §1.7).

A logging filter masks obvious sensitive fields in structured log arguments as a
defence in depth. The primary rule is stronger: auth endpoints never log request
bodies, and no code logs passwords, tokens or ``Set-Cookie`` values.
"""

from __future__ import annotations

import logging
from typing import Any

# Case-insensitive field names that must never appear in logs.
SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "token_hash",
        "secret",
        "authorization",
        "cookie",
        "set-cookie",
        "session",
        "initial_admin_password",
        # F017/DR-310: API Key credential material never appears in logs.
        "api_key",
        "api_key_hash",
        "key_hash",
        "plaintext",
        "bearer",
    }
)


def _is_sensitive(key: object) -> bool:
    return str(key).strip().lower() in SENSITIVE_FIELDS


def redact(value: Any) -> Any:
    """Recursively mask values whose mapping keys are sensitive."""
    if isinstance(value, dict):
        return {
            key: "***" if _is_sensitive(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


class SensitiveDataFilter(logging.Filter):
    """Mask sensitive keys in ``LogRecord.msg`` / ``LogRecord.args``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg)
        if isinstance(record.args, dict):
            record.args = redact(record.args)
        elif isinstance(record.args, tuple):
            record.args = redact(record.args)
        return True


def configure_logging(log_level: str = "INFO") -> None:
    """Attach the redaction filter to the root logger exactly once."""
    root = logging.getLogger()
    root.setLevel(log_level.upper())
    if not any(isinstance(f, SensitiveDataFilter) for f in root.filters):
        root.addFilter(SensitiveDataFilter())