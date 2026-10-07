"""Shared name/code normalisation and validation (D01 §5, DB-D22..DB-D24).

Single authoritative implementation reused by API services today and by
CSV/Excel import later (D01 §7): do not duplicate these rules elsewhere.

Rules:
- ``code``: strip surrounding Unicode whitespace, non-empty, no internal
  whitespace, no control characters (Unicode Cc/Cf), length 1-64 code points,
  case and Unicode (including CJK) preserved. ``code_key`` is the
  case-insensitive full-uniqueness key (internal, never exposed): it folds only
  ASCII ``a-z`` to ``A-Z`` and leaves every other code point (including
  non-ASCII letters such as ``ß`` or the ``ﬁ`` ligature) unchanged, matching the
  locale-independent database CHECK ``translate(btrim(code), ...)``.
- ``name``: strip surrounding whitespace, non-empty, no control characters
  (Cc/Cf), length 1-255 code points; internal ordinary spaces and case are
  preserved; no uniqueness.
"""

from __future__ import annotations

import unicodedata

from app.core.errors import ValidationError

CODE_MAX_LENGTH = 64
NAME_MAX_LENGTH = 255


def _control_characters(value: str) -> bool:
    """Whether ``value`` contains a Unicode Cc/Cf control/format character."""
    return any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in value)


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(details={"fields": [{"field": field, "message": message}]})


def normalize_code(value: str) -> str:
    """Validate and return the trimmed display ``code`` (D01 §5.1)."""
    if not isinstance(value, str):
        raise _field_error("code", "code must be a string")
    normalized = value.strip()
    if not normalized:
        raise _field_error("code", "code must not be blank")
    if len(normalized) > CODE_MAX_LENGTH:
        raise _field_error("code", f"code must be at most {CODE_MAX_LENGTH} characters")
    if any(ch.isspace() for ch in normalized):
        raise _field_error("code", "code must not contain whitespace")
    if _control_characters(normalized):
        raise _field_error("code", "code must not contain control characters")
    return normalized


# ASCII-only case folding: only a-z are folded; non-ASCII code points are kept
# verbatim so Python and PostgreSQL ``translate(btrim(code), ...)`` agree in any
# database locale (review F003-REV-1).
_ASCII_FOLD = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def code_key(code: str) -> str:
    """Return the normalisation key ``translate(btrim(code))`` (DB-D22).

    Only ASCII ``a-z`` are upper-cased; non-ASCII code points are preserved,
    matching the database CHECK constraint and avoiding locale-dependent
    multi-code-point case mappings (``straße`` -> ``STRAßE``, ``ﬁle`` -> ``ﬁLE``).
    """
    return code.strip().translate(_ASCII_FOLD)


def normalize_name(value: str) -> str:
    """Validate and return the trimmed display ``name`` (D01 §5)."""
    if not isinstance(value, str):
        raise _field_error("name", "name must be a string")
    normalized = value.strip()
    if not normalized:
        raise _field_error("name", "name must not be blank")
    if len(normalized) > NAME_MAX_LENGTH:
        raise _field_error("name", f"name must be at most {NAME_MAX_LENGTH} characters")
    if _control_characters(normalized):
        raise _field_error("name", "name must not contain control characters")
    return normalized