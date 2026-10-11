"""Service reference-checker registry (F011 DR-146).

A Service is referenced by ServiceEndpoint rows (F012). F011 ships no Endpoint
table, so the registry defaults to an empty set; :func:`delete_service` already
calls :func:`check_service_references` before the soft delete. F012 registers a
real checker with :func:`register_service_reference_checker` and the end-to-end
``reference_exists`` protection then takes effect without rewiring F011.

This registry is intentionally separate from the shared ``cluster_service``
reference registry, which carries the *cross-object* ``Resource <- Service``
blocker registered directly in :mod:`app.services.service` (DR-147).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# A checker returns a list of reference descriptors (object_type/object_id/
# label). The empty default means "no reference blocks the operation".
ServiceReferenceChecker = Callable[["Session", uuid.UUID], list[dict[str, Any]]]

_CHECKERS: list[ServiceReferenceChecker] = []


def register_service_reference_checker(checker: ServiceReferenceChecker) -> None:
    """Register a ServiceEndpoint (or later) checker for a Service reference."""
    _CHECKERS.append(checker)


def check_service_references(
    db: "Session", service_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Return undeleted references blocking Service deletion (empty in F011)."""
    references: list[dict[str, Any]] = []
    for checker in _CHECKERS:
        references.extend(checker(db, service_id))
    return references