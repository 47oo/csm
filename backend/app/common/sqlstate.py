"""通用 SQLSTATE → HTTP 映射（资源无关，单一实现）。

契约见 ``docs/api/f012-project-foundation.md`` §3：

| SQLSTATE | 含义            | HTTP | error.code       |
|----------|-----------------|------|------------------|
| 23502    | NOT NULL 违反   | 400  | VALIDATION_ERROR |
| 23514    | CHECK 违反      | 400  | VALIDATION_ERROR |
| 23505    | 唯一索引违反    | 409  | CONFLICT         |
| 23503    | 外键违反        | 409  | CONFLICT         |

资源级的产品冲突语义（应用层预检、友好文案）由后续 Feature 在此之上叠加，
**不得另立第二套信封或映射**。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.db.base import Base

# 约束名前缀，用于在数据库未提供列名时回退解析。
_CONSTRAINT_PREFIXES = ("ck_", "ux_", "uq_", "fk_", "ix_", "pk_")


@dataclass(frozen=True)
class SqlStateMapping:
    status_code: int
    error_code: str
    detail_code: str
    message: str


# 单一映射表：SQLSTATE → HTTP 语义。
SQLSTATE_MAP: dict[str, SqlStateMapping] = {
    "23502": SqlStateMapping(400, "VALIDATION_ERROR", "REQUIRED", "字段不能为空"),
    "23514": SqlStateMapping(400, "VALIDATION_ERROR", "CHECK_VIOLATION", "字段值不满足约束"),
    "23505": SqlStateMapping(409, "CONFLICT", "DUPLICATE", "唯一性冲突"),
    "23503": SqlStateMapping(409, "CONFLICT", "REFERENCE", "引用的资源不存在或被引用"),
}


def sqlstate_of(exc: IntegrityError) -> str | None:
    """从 SQLAlchemy ``IntegrityError`` 提取 PostgreSQL SQLSTATE。"""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if pgcode:
        return str(pgcode)
    diag = getattr(orig, "diag", None)
    if diag is not None:
        code = getattr(diag, "sqlstate", None)
        if code:
            return str(code)
    return None


def _diag_value(exc: IntegrityError, name: str) -> str | None:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    if diag is None:
        return None
    value = getattr(diag, name, None)
    return str(value) if value else None


def _field_from_metadata(table_name: str | None, constraint_name: str | None) -> str | None:
    """尝试从 ``Base.metadata`` 的列名中匹配约束名里的字段。"""
    if not table_name or not constraint_name:
        return None
    table = Base.metadata.tables.get(table_name)
    if table is None:
        return None
    matches = [column.name for column in table.columns if column.name in constraint_name]
    if not matches:
        return None
    # 取最长匹配，避免 ``id`` 命中 ``cluster_id`` 之类的误判。
    return max(matches, key=len)


def _field_from_constraint_name(table_name: str | None, constraint_name: str | None) -> str | None:
    if not constraint_name:
        return None
    name = constraint_name
    for prefix in _CONSTRAINT_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    if table_name and name.startswith(f"{table_name}_"):
        name = name[len(table_name) + 1 :]
    # 去掉常见后缀（active / unique / fkey / pkey / check）。
    for suffix in ("_active", "_unique", "_fkey", "_pkey", "_check"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    tokens = [t for t in name.split("_") if t]
    return tokens[0] if tokens else None


def field_for(exc: IntegrityError) -> str | None:
    """尽力判定违规列（契约要求「若可判定」/「至少 name」）。"""
    column = _diag_value(exc, "column_name")
    if column:
        return column
    table_name = _diag_value(exc, "table_name")
    constraint_name = _diag_value(exc, "constraint_name")
    return _field_from_metadata(table_name, constraint_name) or _field_from_constraint_name(
        table_name, constraint_name
    )


def map_integrity_error(exc: IntegrityError) -> tuple[int, str, list[dict[str, str | None]]] | None:
    """把 ``IntegrityError`` 映射为 ``(status_code, error_code, details)``。

    未识别（非本映射覆盖）的 SQLSTATE 返回 ``None``，由调用方按 500 处理。
    """
    sqlstate = sqlstate_of(exc)
    if sqlstate is None or sqlstate not in SQLSTATE_MAP:
        return None
    mapping = SQLSTATE_MAP[sqlstate]
    detail: dict[str, str | None] = {
        "field": field_for(exc),
        "code": mapping.detail_code,
        "message": mapping.message,
    }
    return mapping.status_code, mapping.error_code, [detail]
