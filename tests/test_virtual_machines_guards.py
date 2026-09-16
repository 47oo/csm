"""F006 VirtualMachine 静态 / 结构 guard（G-1 ~ G-11、T-26、T-27）。

把「字段封闭」「未定义约束不实现」「活跃子检查点显式声明且被消费」「唯一软删写入
路径」「无 EAV / JSONB / 多态」「路由交付面封闭」变成会失败的测试，而非口头约定。
"""

from __future__ import annotations

from app.bare_metals.deletion import BARE_METAL_ACTIVE_CHILD_CHECKS
from app.virtual_machines.deletion import (
    VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS,
    has_active_virtual_machines,
)
from app.virtual_machines.router import router as virtual_machines_router
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
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

VM_READ_FIELDS = {
    "id",
    "bare_metal_id",
    "name",
    "cpu",
    "memory",
    "disk",
    "os",
    "hypervisor",
    "owner",
    "created_at",
    "updated_at",
}

OPTIONAL_FIELDS = ("cpu", "memory", "disk", "os", "hypervisor", "owner")


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
# 字段封闭（契约 §2）
# --------------------------------------------------------------------------- #
def test_vm_read_schema_is_closed():
    from app.virtual_machines.schemas import VirtualMachineRead

    assert set(VirtualMachineRead.model_fields) == VM_READ_FIELDS
    assert "deleted_at" not in VirtualMachineRead.model_fields
    assert "status" not in VirtualMachineRead.model_fields
    assert "cluster_id" not in VirtualMachineRead.model_fields


def test_vm_create_and_update_schemas_closed():
    from app.virtual_machines.schemas import VirtualMachineCreate, VirtualMachineUpdate

    assert VirtualMachineCreate.model_config.get("extra") == "forbid"
    assert VirtualMachineUpdate.model_config.get("extra") == "forbid"

    assert "bare_metal_id" in VirtualMachineCreate.model_fields
    assert "name" in VirtualMachineCreate.model_fields
    assert set(VirtualMachineCreate.model_fields) == {"bare_metal_id", "name", *OPTIONAL_FIELDS}

    assert set(VirtualMachineUpdate.model_fields) == set(OPTIONAL_FIELDS)
    for forbidden in ("name", "bare_metal_id", "id", "deleted_at", "status"):
        assert forbidden not in VirtualMachineUpdate.model_fields


# --------------------------------------------------------------------------- #
# G-4：EXPECTED_GET_ROUTES 追加 VM 两条 GET 路由（只增不删）
# --------------------------------------------------------------------------- #
def test_g4_expected_get_routes_contains_vm_routes():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES

    assert "/api/virtual-machines" in EXPECTED_GET_ROUTES
    assert "/api/virtual-machines/{virtual_machine_id}" in EXPECTED_GET_ROUTES


# --------------------------------------------------------------------------- #
# G-5 / T-26：BARE_METAL_ACTIVE_CHILD_CHECKS 非空且含活跃 VM 检查
# --------------------------------------------------------------------------- #
def test_g5_t26_bare_metal_active_child_checks_contain_vm_check():
    assert isinstance(BARE_METAL_ACTIVE_CHILD_CHECKS, tuple)
    assert len(BARE_METAL_ACTIVE_CHILD_CHECKS) >= 1, "BareMetal 删除守卫不得 fail-open 为空"
    assert has_active_virtual_machines in BARE_METAL_ACTIVE_CHILD_CHECKS


def test_t26_bare_metal_delete_path_consumes_declared_checks():
    source = (REPO_ROOT / "backend/app/bare_metals/service.py").read_text(encoding="utf-8")
    assert "BARE_METAL_ACTIVE_CHILD_CHECKS" in source
    assert "soft_delete(" in source


def test_t26_bare_metal_active_child_check_blocks_delete(auth_client_and_raw, monkeypatch):
    """声明被真实消费：注入命中检查 → 409 且无部分写入；空检查时同一路径成功。"""
    client, conn = auth_client_and_raw
    cluster_id = client.post("/api/clusters", json={"name": "cluster-a"}).json()["id"]
    host = client.post("/api/bare-metals", json={"cluster_id": cluster_id, "hostname": "n1"}).json()

    monkeypatch.setattr(
        "app.bare_metals.service.BARE_METAL_ACTIVE_CHILD_CHECKS",
        (lambda session, parent_id: True,),
    )
    blocked = client.delete(f"/api/bare-metals/{host['id']}")
    assert blocked.status_code == 409
    assert any(
        detail["code"] == "ACTIVE_CHILDREN_EXIST" for detail in blocked.json()["error"]["details"]
    )
    assert (
        conn.execute("SELECT deleted_at FROM bare_metals WHERE id = %s", (host["id"],)).fetchone()[
            0
        ]
        is None
    )

    monkeypatch.setattr("app.bare_metals.service.BARE_METAL_ACTIVE_CHILD_CHECKS", ())
    assert client.delete(f"/api/bare-metals/{host['id']}").status_code == 204


# --------------------------------------------------------------------------- #
# G-6 / T-27：VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS 显式声明且被删除路径传入
# --------------------------------------------------------------------------- #
def test_g6_t27_vm_active_child_checks_explicitly_declared():
    assert isinstance(VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS, tuple)
    assert VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS == ()
    source = (REPO_ROOT / "backend/app/virtual_machines/deletion.py").read_text(encoding="utf-8")
    assert "VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS" in source
    assert "= ()" in source, "必须显式声明空元组，而非隐式缺省"


def test_g6_t27_vm_delete_path_passes_active_child_checks():
    source = (REPO_ROOT / "backend/app/virtual_machines/service.py").read_text(encoding="utf-8")
    assert "soft_delete(" in source, "VirtualMachine 删除必须委托统一软删服务"
    assert "VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS" in source, "必须显式传入声明的活跃子检查"


# --------------------------------------------------------------------------- #
# G-7：未定义约束「不实现」
# --------------------------------------------------------------------------- #
def test_g7_vm_schemas_have_no_undefined_constraints():
    from app.virtual_machines.schemas import VirtualMachineCreate, VirtualMachineUpdate

    for model in (VirtualMachineCreate, VirtualMachineUpdate):
        for field in OPTIONAL_FIELDS:
            assert _field_constraint_flags(model, field) == set(), f"{model.__name__}.{field}"
        decorators = model.__pydantic_decorators__
        assert decorators.validators == {}
        assert decorators.field_validators == {}
    assert _field_constraint_flags(VirtualMachineCreate, "name") == set()
    assert VirtualMachineCreate.__pydantic_decorators__.validators == {}
    assert VirtualMachineCreate.__pydantic_decorators__.field_validators == {}


# --------------------------------------------------------------------------- #
# G-9：唯一软删写入路径 allow-list 不变；VM 模块不写 deleted_at
# --------------------------------------------------------------------------- #
def test_g9_deleted_at_writer_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


def test_g9_vm_module_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "virtual_machines") == {}


# --------------------------------------------------------------------------- #
# G-10：无通用表 / EAV / JSON(B) / 多态（对 virtual_machines 继续成立）
# --------------------------------------------------------------------------- #
def test_g10_no_generic_eav_json_or_polymorphic_for_vm():
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import configure_mappers

    from app.db.base import Base

    table = Base.metadata.tables["virtual_machines"]
    for column in table.columns:
        assert not isinstance(column.type, (JSON, JSONB)), column.name
    assert table.name not in ("resources",)
    assert "resource" not in table.name

    configure_mappers()
    offenders = [m.class_.__name__ for m in Base.registry.mappers if m.polymorphic_on is not None]
    assert offenders == []


# --------------------------------------------------------------------------- #
# G-11：MIGRATION_HEAD 与 0004 一致
# --------------------------------------------------------------------------- #
def test_g11_migration_head_is_0004():
    from tests.database.helpers import MIGRATION_HEAD

    assert MIGRATION_HEAD == "0004_f006_virtual_machines"


# --------------------------------------------------------------------------- #
# G-1：ORM 元数据列集合恰为 12 列；无 status / cluster_id
# --------------------------------------------------------------------------- #
def test_g1_model_metadata_columns_exact():
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["virtual_machines"].columns}
    assert columns == {
        "id",
        "bare_metal_id",
        "name",
        *OPTIONAL_FIELDS,
        "created_at",
        "updated_at",
        "deleted_at",
    }
    assert "status" not in columns
    assert "cluster_id" not in columns


# --------------------------------------------------------------------------- #
# G-2：ORM 索引（partial unique + 宿主索引）与 RESTRICT FK
# --------------------------------------------------------------------------- #
def test_g2_model_indexes_and_fk():
    from app.db.base import Base

    table = Base.metadata.tables["virtual_machines"]
    index_names = {index.name for index in table.indexes}
    assert "ux_virtual_machines_name_active" in index_names
    assert "ix_virtual_machines_bare_metal_id" in index_names

    unique_name_index = next(
        index for index in table.indexes if index.name == "ux_virtual_machines_name_active"
    )
    assert unique_name_index.unique is True

    fk = next(iter(table.foreign_keys))
    assert fk.name == "fk_virtual_machines_bare_metal"
    assert fk.ondelete == "RESTRICT"
    assert fk.onupdate == "RESTRICT"


# --------------------------------------------------------------------------- #
# G-交付面：VM 路由恰为 5 个端点
# --------------------------------------------------------------------------- #
def test_vm_router_registers_exactly_five_endpoints():
    routes = {
        (method, route.path) for route in virtual_machines_router.routes for method in route.methods
    }
    assert routes == {
        ("POST", "/virtual-machines"),
        ("GET", "/virtual-machines"),
        ("GET", "/virtual-machines/{virtual_machine_id}"),
        ("PATCH", "/virtual-machines/{virtual_machine_id}"),
        ("DELETE", "/virtual-machines/{virtual_machine_id}"),
    }
