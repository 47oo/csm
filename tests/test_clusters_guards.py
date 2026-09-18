"""F001 负向 guard：未定义约束不实现 + 单一路径 / 自检面彻底移除。

这些 guard 让「不实现未定义约束」「不存在第二条删除路径」「自检面已移除」
成为**会失败的测试**，而非口头约定（Q8 / AC-13 / ADR-0004）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clusters.schemas import ClusterCreate, ClusterUpdate
from tests.conftest import OFFLINE_DSN, _client
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    scan_deleted_at_writes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "backend" / "app"

# 这些约束一旦出现在 name 字段上，即视为违反了 undefined_constraints 的
# 「不得自行假设」指令。
_FORBIDDEN_CONSTRAINT_ATTRS = (
    "min_length",
    "max_length",
    "pattern",
    "strip_whitespace",
    "to_lower",
    "to_upper",
)


def _name_constraint_flags(model) -> set[str]:
    field = model.model_fields["name"]
    flags: set[str] = set()
    for meta in field.metadata:
        for attr in _FORBIDDEN_CONSTRAINT_ATTRS:
            value = getattr(meta, attr, None)
            if value not in (None, False):
                flags.add(attr)
    config = model.model_config
    for attr in ("str_strip_whitespace", "str_to_lower", "str_to_upper"):
        if config.get(attr):
            flags.add(attr)
    return flags


# --------------------------------------------------------------------------- #
# G1 / Q8 / NQ-1：schema 层不得对 name 施加未定义约束
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("model", [ClusterCreate, ClusterUpdate])
def test_g1_name_has_no_undefined_constraints(model):
    assert _name_constraint_flags(model) == set()

    # 不得存在对 name 施加 trim / NFC / 非空串的 validator。
    decorators = model.__pydantic_decorators__
    assert decorators.validators == {}
    assert decorators.field_validators == {}


# --------------------------------------------------------------------------- #
# A14 / AC-13：自检面已彻底移除（dev 与 prod 均不可达 + 静态）
# --------------------------------------------------------------------------- #
_FOUNDATION_REQUESTS = [
    ("GET", "/_foundation/clusters"),
    ("POST", "/_foundation/clusters"),
    ("GET", "/_foundation/clusters/1"),
    ("PATCH", "/_foundation/clusters/1"),
    ("DELETE", "/_foundation/clusters/1"),
    ("GET", "/_foundation/error"),
]


@pytest.fixture
def prod_client() -> TestClient:
    with _client("prod", OFFLINE_DSN) as client:
        yield client


@pytest.mark.parametrize("environment", ["dev", "prod"])
@pytest.mark.parametrize(("method", "path"), _FOUNDATION_REQUESTS)
def test_a14_foundation_face_absent_in_any_config(environment, method, path):
    with _client(environment, OFFLINE_DSN) as client:
        response = client.request(method, path, json={"name": "x"})
    assert response.status_code == 404, f"{method} {path}（{environment}）必须 404"
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a14_no_foundation_string_in_app_source():
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if "_foundation" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"app 源码中仍残留 _foundation：{offenders}"


def test_a14_foundation_package_directory_removed():
    assert not (APP_DIR / "foundation").exists()


def test_a14_settings_has_no_foundation_enabled():
    from app.config import Settings

    settings = Settings()
    assert not hasattr(settings, "foundation_enabled")


# --------------------------------------------------------------------------- #
# A15 静态部分 / ADR-0004 → F014 G-3：写入 deleted_at 的文件恰好为统一软删服务
# --------------------------------------------------------------------------- #
def test_a15_deleted_at_write_paths_are_allowlisted():
    """F014 后写入路径由 0 处演进的「恰好 1 处文件」，避免验证力静默丢失。

    唯一权威断言（含无 undelete）在 ``tests/test_deletion_guards.py::test_g3_*``；
    本用例保留 F001 A15 的历史入口，复用同一扫描器。
    """
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"
