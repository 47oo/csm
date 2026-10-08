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
- ``hostname`` (F004, D01 §5.3): strip surrounding Unicode whitespace,
  non-empty, no internal whitespace (Unicode White_Space), no control/format
  characters (Cc/Cf), length 1-253 code points, then fold only ASCII ``A-Z`` to
  ``a-z`` (non-ASCII kept verbatim, locale-independent). ``hostname_key`` is the
  corresponding internal normalisation key (redundant because the display value
  is already trimmed and ASCII-lowered), matching the database
  ``translate(btrim(hostname), ...)`` CHECK. ``str.lower()`` must NOT be used
  (it maps ``İ``/``ß`` inconsistently with the database).
- ``hardware`` string (F005, D01 §5.4): strip surrounding whitespace, non-empty
  (empty/whitespace-only is a 422, never ``null``), no Cc/Cf, length <= 255 code
  points, no case folding and no uniqueness.
- ``interface_name`` (F007, D01 §5.6): strip surrounding whitespace, non-empty,
  no internal whitespace (Unicode White_Space), no Cc/Cf, length 1-64 code
  points, case preserved; uniqueness is the (resource_id, name) partial unique
  index, not computed here.
- ``mac_address`` (F007, D01 §5.6): strip surrounding whitespace, non-empty
  (empty/whitespace-only is a 422, never ``null``), no Cc/Cf, length <= 64 code
  points, case preserved, no format regex and no uniqueness.
"""

from __future__ import annotations

import unicodedata

from app.core.errors import ValidationError

CODE_MAX_LENGTH = 64
NAME_MAX_LENGTH = 255
HOSTNAME_MAX_LENGTH = 253
HARDWARE_STRING_MAX_LENGTH = 255
INTERFACE_NAME_MAX_LENGTH = 64
MAC_ADDRESS_MAX_LENGTH = 64


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


# ASCII-only lower-case folding for Resource hostnames (D01 §5.3, DB-D36).
_ASCII_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
)


def normalize_hostname(value: str) -> str:
    """Validate and return the trimmed, ASCII-only lower ``hostname`` (D01 §5.3).

    Trim -> non-empty -> no internal whitespace -> no Cc/Cf control characters ->
    length 1-253 code points -> fold ASCII ``A-Z`` to ``a-z`` (non-ASCII code
    points kept verbatim). Short names and FQDNs are distinct complete strings.
    """
    if not isinstance(value, str):
        raise _field_error("hostname", "hostname must be a string")
    normalized = value.strip()
    if not normalized:
        raise _field_error("hostname", "hostname must not be blank")
    if len(normalized) > HOSTNAME_MAX_LENGTH:
        raise _field_error(
            "hostname", f"hostname must be at most {HOSTNAME_MAX_LENGTH} characters"
        )
    if any(ch.isspace() for ch in normalized):
        raise _field_error("hostname", "hostname must not contain whitespace")
    if _control_characters(normalized):
        raise _field_error("hostname", "hostname must not contain control characters")
    return normalized.translate(_ASCII_LOWER)


def hostname_key(hostname: str) -> str:
    """Return the internal key ``ASCII_lower(btrim(hostname))`` (DB-D36).

    Because :func:`normalize_hostname` already returns a trimmed, ASCII-lowered
    value, this is normally identical to the stored display value; it exists so
    the database CHECK ``hostname_key = translate(btrim(hostname), ...)`` and the
    application compute the key the same way. ``str.lower()`` must not be used.
    """
    return hostname.strip().translate(_ASCII_LOWER)


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


def validate_descriptive_string(field: str, value: str, *, max_length: int) -> str:
    """Validate a trimmed, non-empty descriptive string (D01 §5.4/§5.5).

    Trim surrounding whitespace -> non-empty -> no Cc/Cf control characters ->
    length <= ``max_length`` code points. Empty / whitespace-only becomes a 422
    ``ValidationError`` (never ``null``); explicit ``null`` is handled by the
    caller before this function is reached. No case folding, no uniqueness.
    Shared by BareMetal hardware strings and the VM hypervisor.
    """
    if not isinstance(value, str):
        raise _field_error(field, f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise _field_error(field, f"{field} must not be blank")
    if len(normalized) > max_length:
        raise _field_error(
            field,
            f"{field} must be at most {max_length} characters",
        )
    if _control_characters(normalized):
        raise _field_error(field, f"{field} must not contain control characters")
    return normalized


def validate_hardware_string(field: str, value: str) -> str:
    """Validate a BareMetal hardware string field (D01 §5.4, DR-52).

    Trim surrounding whitespace -> non-empty -> no Cc/Cf control characters ->
    length <= 255 code points. Empty / whitespace-only becomes a 422
    ``ValidationError`` (never ``null``); explicit ``null`` is handled by the
    caller before this function is reached. No case folding, no uniqueness.
    """
    return validate_descriptive_string(
        field, value, max_length=HARDWARE_STRING_MAX_LENGTH
    )


def normalize_interface_name(value: str) -> str:
    """Validate and return the trimmed Interface ``name`` (D01 §5.6, DR-73).

    Trim surrounding whitespace -> non-empty -> no internal whitespace (Unicode
    White_Space) -> no Cc/Cf control characters -> length 1-64 code points.
    Case is preserved verbatim (``eth0`` and ``ETH0`` are different names); no
    uniqueness is applied here (the (resource_id, name) partial unique index and
    the Service layer own that). Matches the ASCII-only database CHECK backstop
    ``ck_interfaces_name_no_ws_control`` for the common case; Unicode Cc/Cf is
    an application responsibility.
    """
    if not isinstance(value, str):
        raise _field_error("name", "name must be a string")
    normalized = value.strip()
    if not normalized:
        raise _field_error("name", "name must not be blank")
    if any(ch.isspace() for ch in normalized):
        raise _field_error("name", "name must not contain whitespace")
    if _control_characters(normalized):
        raise _field_error("name", "name must not contain control characters")
    if len(normalized) > INTERFACE_NAME_MAX_LENGTH:
        raise _field_error(
            "name",
            f"name must be at most {INTERFACE_NAME_MAX_LENGTH} characters",
        )
    return normalized


def normalize_mac_address(value: str) -> str:
    """Validate and return the trimmed Interface ``mac_address`` (D01 §5.6).

    Trim surrounding whitespace -> non-empty -> no Cc/Cf control characters ->
    length <= 64 code points. Empty / whitespace-only becomes a 422
    ``ValidationError`` (never ``null``); explicit ``null`` is handled by the
    caller. No format regex, case preserved, no uniqueness (DR-75).
    """
    if not isinstance(value, str):
        raise _field_error("mac_address", "mac_address must be a string")
    normalized = value.strip()
    if not normalized:
        raise _field_error("mac_address", "mac_address must not be blank")
    if _control_characters(normalized):
        raise _field_error(
            "mac_address", "mac_address must not contain control characters"
        )
    if len(normalized) > MAC_ADDRESS_MAX_LENGTH:
        raise _field_error(
            "mac_address",
            f"mac_address must be at most {MAC_ADDRESS_MAX_LENGTH} characters",
        )
    return normalized