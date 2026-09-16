"""F002 静态 / 结构 guard（T-22、T-27、G-4、G-5、G-7）。

把「显式声明活跃子资源检查点」「Cluster 检查非空且被消费」「唯一软删写入路径」
「未定义约束不实现」「无 EAV / JSONB」变成会失败的测试，而非口头约定。
"""

from __future__ import annotations

from app.bare_metals.deletion import BARE_METAL_ACTIVE_CHILD_CHECKS
from app.clusters.deletion import CLUSTER_ACTIVE_CHILD_CHECKS
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    REPO_ROOT,
    scan_deleted_at_writes,
)

FORBIDDEN_CONSTRAINT_ATTRS = (
    "min_length",
    "max_length",
    "pattern",
    "strip_whitespace",
    "to_lower",
    "to_upper",
)


def _field_constraint_flags(model, field_name: str) -> set[str]:
    field = model.model_fields[field_name]
    flags: set[str] = set()
    for meta in field.metadata:
        for attr in FORBIDDEN_CONSTRAINT_ATTRS:
            if getattr(meta, attr, None) not in (None, False):
                flags.add(attr)
    for attr in ("str_strip_whitespace", "str_to_lower", "str_to_upper"):
        if model.model_config.get(attr):
            flags.add(attr)
    return flags


# --------------------------------------------------------------------------- #
# T-22 / AC-22：BareMetal 活跃子检查点显式声明，并被删除路径真实传入
# --------------------------------------------------------------------------- #
def test_t22_bare_metal_active_child_checks_explicitly_declared():
    # F006 演进：BARE_METAL_ACTIVE_CHILD_CHECKS 由显式空元组演进为包含「活跃
    # VirtualMachine」检查（R-VM-005 / AC-28）；不再允许 fail-open 的空元组。
    from app.virtual_machines.deletion import has_active_virtual_machines

    assert isinstance(BARE_METAL_ACTIVE_CHILD_CHECKS, tuple)
    assert len(BARE_METAL_ACTIVE_CHILD_CHECKS) >= 1
    assert has_active_virtual_machines in BARE_METAL_ACTIVE_CHILD_CHECKS
    source = (REPO_ROOT / "backend/app/bare_metals/deletion.py").read_text(encoding="utf-8")
    assert "BARE_METAL_ACTIVE_CHILD_CHECKS" in source
    assert "has_active_virtual_machines" in source, "必须显式声明活跃 VM 检查"


def test_t22_delete_path_passes_active_child_checks(auth_client_and_raw, monkeypatch):
    client, conn = auth_client_and_raw
    cluster_id = client.post("/api/clusters", json={"name": "cluster-a"}).json()["id"]
    created = client.post(
        "/api/bare-metals", json={"cluster_id": cluster_id, "hostname": "n1"}
    ).json()

    # 显式声明被真实消费：注入命中检查 → 409 且无部分写入。
    monkeypatch.setattr(
        "app.bare_metals.service.BARE_METAL_ACTIVE_CHILD_CHECKS",
        (lambda session, parent_id: True,),
    )
    blocked = client.delete(f"/api/bare-metals/{created['id']}")
    assert blocked.status_code == 409
    assert any(
        detail["code"] == "ACTIVE_CHILDREN_EXIST" for detail in blocked.json()["error"]["details"]
    )
    assert (
        conn.execute(
            "SELECT deleted_at FROM bare_metals WHERE id = %s", (created["id"],)
        ).fetchone()[0]
        is None
    )

    # 检查为空时同一路径成功（证明拒绝来自守卫，而非端点不可用）。
    monkeypatch.setattr("app.bare_metals.service.BARE_METAL_ACTIVE_CHILD_CHECKS", ())
    assert client.delete(f"/api/bare-metals/{created['id']}").status_code == 204


def test_t22_delete_bare_metal_delegates_to_soft_delete():
    source = (REPO_ROOT / "backend/app/bare_metals/service.py").read_text(encoding="utf-8")
    assert "soft_delete(" in source, "BareMetal 删除必须委托统一软删服务"
    assert "BARE_METAL_ACTIVE_CHILD_CHECKS" in source, "必须显式传入声明的活跃子检查"


# --------------------------------------------------------------------------- #
# T-27 / AC-27 / F014 NOTE-01：Cluster 活跃子检查非空且包含 BareMetal 检查
# --------------------------------------------------------------------------- #
def test_t27_cluster_active_child_checks_is_not_empty():
    from app.bare_metals.deletion import has_active_bare_metals

    assert len(CLUSTER_ACTIVE_CHILD_CHECKS) >= 1, "Cluster 删除守卫不得 fail-open 为空元组"
    assert has_active_bare_metals in CLUSTER_ACTIVE_CHILD_CHECKS


def test_t27_cluster_delete_path_consumes_declared_checks():
    source = (REPO_ROOT / "backend/app/clusters/service.py").read_text(encoding="utf-8")
    assert "CLUSTER_ACTIVE_CHILD_CHECKS" in source
    assert "soft_delete(" in source


# --------------------------------------------------------------------------- #
# G-4 / ADR-0004：唯一软删写入路径仍恰为 deletion/service.py
# --------------------------------------------------------------------------- #
def test_g4_deleted_at_writer_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


def test_g4_bare_metal_module_writes_no_deleted_at():
    hits = scan_deleted_at_writes(REPO_ROOT / "backend/app/bare_metals")
    assert hits == {}, f"BareMetal 模块不得写 deleted_at：{hits}"


# --------------------------------------------------------------------------- #
# G-5：schema 层不得对 hostname 施加未定义约束
# --------------------------------------------------------------------------- #
def test_g5_hostname_has_no_undefined_constraints():
    from app.bare_metals.schemas import BareMetalCreate

    assert _field_constraint_flags(BareMetalCreate, "hostname") == set()
    for model in (BareMetalCreate,):
        decorators = model.__pydantic_decorators__
        assert decorators.validators == {}
        assert decorators.field_validators == {}


def test_g5_hardware_fields_have_no_constraints():
    from app.bare_metals.schemas import HARDWARE_FIELDS, BareMetalCreate, BareMetalUpdate

    for model in (BareMetalCreate, BareMetalUpdate):
        for field in HARDWARE_FIELDS:
            assert _field_constraint_flags(model, field) == set(), f"{model.__name__}.{field}"


# --------------------------------------------------------------------------- #
# G-7：无 EAV / 通用表 / JSONB / 多态（对 bare_metals 继续成立）
# --------------------------------------------------------------------------- #
def test_g7_no_generic_or_eav_or_json_columns():
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    from app.db.base import Base

    table = Base.metadata.tables["bare_metals"]
    for column in table.columns:
        assert not isinstance(column.type, (JSON, JSONB)), column.name
    assert table.name not in ("resources",)
    assert "resource" not in table.name
