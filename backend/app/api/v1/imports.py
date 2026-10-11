"""F014 CSV / Excel import REST endpoints (Contract §3/§4/§5).

Routes stay thin: permission/format checks and response shaping; all parsing,
validation, atomicity and writes live in
:mod:`app.services.resource_import`.

Validation order follows Contract §2: authentication (401) -> permission (403)
-> ``format`` shape (422) -> file size (413) -> parse (422) -> row limit (413)
-> header/columns (422) -> per-row validation. The auth/permission dependencies
are resolved by FastAPI before the body is parsed, so they precede ``format``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import Operator
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ValidationError
from app.core.permissions import Permission, require_permission
from app.schemas.imports import (
    ImportTemplatesResponse,
    ImportValidateResponse,
    ImportWriteResponse,
)
from app.services import resource_import

router = APIRouter(prefix="/imports", tags=["imports"])

_SUPPORTED_FORMATS = ("csv", "xlsx")


def _normalize_format(value: str) -> str:
    """Case-insensitive ``csv``/``xlsx`` check; anything else is 422 field=format."""
    fmt = (value or "").strip().lower()
    if fmt not in _SUPPORTED_FORMATS:
        raise ValidationError(
            details={
                "fields": [
                    {"field": "format", "message": "format must be csv or xlsx"}
                ]
            }
        )
    return fmt


@router.get("/resources/templates", response_model=ImportTemplatesResponse)
def get_import_templates(
    operator: Operator = Depends(require_permission(Permission.READ)),
) -> ImportTemplatesResponse:
    """Frozen template specification (A25); read-only, no Audit, idempotent."""
    return ImportTemplatesResponse(**{"templates": resource_import.templates_payload()})


@router.post("/resources/validate", response_model=ImportValidateResponse)
def validate_import(
    file: UploadFile = File(...),
    format: str = Form(...),
    operator: Operator = Depends(require_permission(Permission.IMPORT)),
    db: Session = Depends(get_db),
) -> ImportValidateResponse:
    """Read-only pre-validate: parse + aggregate every row error (Contract §3)."""
    settings = get_settings()
    fmt = _normalize_format(format)
    data = file.file.read()
    result = resource_import.validate_import(db, data, fmt, settings)
    return ImportValidateResponse(**resource_import.result_payload(result, settings))


@router.post("/resources", response_model=ImportWriteResponse, status_code=201)
def write_import(
    file: UploadFile = File(...),
    format: str = Form(...),
    operator: Operator = Depends(require_permission(Permission.IMPORT)),
    db: Session = Depends(get_db),
) -> ImportWriteResponse:
    """Re-validate and insert the batch atomically (Contract §4, DR-203)."""
    settings = get_settings()
    fmt = _normalize_format(format)
    data = file.file.read()
    created, total_rows = resource_import.write_import(
        db, operator, data, fmt, settings
    )
    return ImportWriteResponse(created=created, total_rows=total_rows)