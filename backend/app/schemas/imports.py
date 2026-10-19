"""F014 import schemas (Contract §3/§4/§5).

Response-only models: request bodies are ``multipart/form-data`` handled in
:mod:`app.api.v1.imports`. ``format`` is the normalised request format; the
validate response carries the aggregate row errors and the frozen template
endpoint exposes the per-column specification.
"""

from __future__ import annotations

from pydantic import BaseModel


class ImportColumnSpec(BaseModel):
    name: str
    required: bool
    target: str
    type: str
    unit: str | None
    enum: list[str] | None
    description: str
    example: str


class ImportTemplateSpec(BaseModel):
    resource_type: str
    columns: list[ImportColumnSpec]


class ImportTemplatesResponse(BaseModel):
    templates: list[ImportTemplateSpec]


class RowErrorOut(BaseModel):
    row: int
    field: str
    reason: str
    related_row: int | None


class ImportValidateResponse(BaseModel):
    format: str
    total_rows: int
    importable_rows: int
    error_count: int
    errors: list[RowErrorOut]
    errors_truncated: bool


class ImportWriteResponse(BaseModel):
    created: int
    total_rows: int


class UnifiedImportColumnSpec(BaseModel):
    name: str
    required: bool
    applies_to: list[str]
    target: str
    type: str
    unit: str | None
    enum: list[str] | None
    description: str
    example: str


class UnifiedImportTemplateSpec(BaseModel):
    key: str
    columns: list[UnifiedImportColumnSpec]


class UnifiedImportTemplatesResponse(BaseModel):
    template: UnifiedImportTemplateSpec


class UnifiedImportWriteResponse(BaseModel):
    created: int
    total_rows: int
    interfaces_created: int
    ip_addresses_created: int