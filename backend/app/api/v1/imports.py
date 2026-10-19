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
    UnifiedImportTemplatesResponse,
    UnifiedImportWriteResponse,
)
from app.services import resource_import
from app.services import resource_interface_ip_import as unified_import

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


# --- F023: resource + interface + IP bulk import (Contract F023 §3/§4/§5) ----


@router.get(
    "/resource-interfaces-ips/templates",
    response_model=UnifiedImportTemplatesResponse,
)
def get_resource_interface_ip_templates(
    operator: Operator = Depends(require_permission(Permission.READ)),
) -> UnifiedImportTemplatesResponse:
    """Frozen unified 26-column template specification; read-only (F023 §5)."""
    return UnifiedImportTemplatesResponse(
        **{"template": unified_import.templates_payload()}
    )


@router.post(
    "/resource-interfaces-ips/validate", response_model=ImportValidateResponse
)
def validate_resource_interface_ip_import(
    file: UploadFile = File(...),
    format: str = Form(...),
    operator: Operator = Depends(require_permission(Permission.IMPORT)),
    db: Session = Depends(get_db),
) -> ImportValidateResponse:
    """Read-only pre-validate: parse + aggregate every row error (F023 §3)."""
    settings = get_settings()
    fmt = _normalize_format(format)
    data = file.file.read()
    result = unified_import.validate_import(db, data, fmt, settings)
    return ImportValidateResponse(**unified_import.result_payload(result, settings))


@router.post(
    "/resource-interfaces-ips",
    response_model=UnifiedImportWriteResponse,
    status_code=201,
)
def write_resource_interface_ip_import(
    file: UploadFile = File(...),
    format: str = Form(...),
    operator: Operator = Depends(require_permission(Permission.IMPORT)),
    db: Session = Depends(get_db),
) -> UnifiedImportWriteResponse:
    """Re-validate and insert the batch atomically (F023 §4, DR-419)."""
    settings = get_settings()
    fmt = _normalize_format(format)
    data = file.file.read()
    (
        created,
        interfaces_created,
        ip_addresses_created,
        total_rows,
    ) = unified_import.write_import(db, operator, data, fmt, settings)
    return UnifiedImportWriteResponse(
        created=created,
        total_rows=total_rows,
        interfaces_created=interfaces_created,
        ip_addresses_created=ip_addresses_created,
    )