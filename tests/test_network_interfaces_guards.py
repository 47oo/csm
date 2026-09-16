"""F004 NetworkInterface 静态 / 结构 guard（G-1 ~ G-14）。

把「字段封闭」「无 IP / 硬件 / 载体字段」「无名称唯一性」「未定义约束不实现」
「活跃子检查点显式声明且被消费」「唯一软删写入路径」「无 EAV / JSONB / 多态」
「路由交付面封闭」变成会失败的测试，而非口头约定。
"""

from __future__ import annotations

import ast

from app.bare_metals.deletion import BARE_METAL_ACTIVE_CHILD_CHECKS
from app.network_interfaces.deletion import (
    NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS,
    has_active_network_interfaces,
)
from app.network_interfaces.router import router as network_interfaces_router
from app.network_interfaces.validation import PURPOSE_VALUES, TECHNOLOGY_TYPE_VALUES
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

NIC_READ_FIELDS = {
    "id",
    "bare_metal_id",
    "name",
    "technology_type",
    "purpose",
    "created_at",
    "updated_at",
}

NIC_TABLE_COLUMNS = {*NIC_READ_FIELDS, "deleted_at"}

FORBIDDEN_COLUMN_TOKENS = (
    "status",
    "ip",
    "ip_address",
    "ipv4",
    "ipv6",
    "prefix_len",
    "mac",
    "mac_address",
    "speed",
    "rate",
    "mtu",
    "port",
    "module",
    "transceiver",
    "discovered",
    "external_id",
    "last_seen",
    "vm_id",
    "virtual_machine_id",
    "container_id",
    "service_id",
    "cluster_id",
    "carrier_type",
    "owner_type",
)

UNIQUENESS_PREFLIGHT_TOKENS = (
    "name_exists",
    "active_name_exists",
    "exists_by_name",
    "duplicate_name",
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


def _soft_delete_active_children_args(source: str) -> list[str]:
    """AST 扫描全部 ``soft_delete(...)`` 调用中 ``active_children=`` 实参的源码文本。"""
    values: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        callee = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if callee != "soft_delete":
            continue
        for keyword in node.keywords:
            if keyword.arg == "active_children":
                values.append(ast.unparse(keyword.value))
    return values


def _nic_module_sources() -> list[tuple[str, str]]:
    return [
        (str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8"))
        for path in sorted((APP_DIR / "network_interfaces").rglob("*.py"))
    ]


# --------------------------------------------------------------------------- #
# 字段封闭（契约 §2）
# --------------------------------------------------------------------------- #
def test_nic_read_schema_is_closed():
    from app.network_interfaces.schemas import NetworkInterfaceRead

    assert set(NetworkInterfaceRead.model_fields) == NIC_READ_FIELDS
    assert "deleted_at" not in NetworkInterfaceRead.model_fields
    assert "status" not in NetworkInterfaceRead.model_fields
    assert "cluster_id" not in NetworkInterfaceRead.model_fields


def test_nic_create_and_update_schemas_closed():
    from app.network_interfaces.schemas import (
        MUTABLE_FIELDS,
        NetworkInterfaceCreate,
        NetworkInterfaceUpdate,
    )

    assert NetworkInterfaceCreate.model_config.get("extra") == "forbid"
    assert NetworkInterfaceUpdate.model_config.get("extra") == "forbid"

    assert set(NetworkInterfaceCreate.model_fields) == {
        "bare_metal_id",
        "name",
        "technology_type",
        "purpose",
    }
    assert set(NetworkInterfaceUpdate.model_fields) == {"technology_type", "purpose"}
    assert MUTABLE_FIELDS == ("technology_type", "purpose")
    for forbidden in ("name", "bare_metal_id", "id", "deleted_at", "status", "created_at"):
        assert forbidden not in NetworkInterfaceUpdate.model_fields


# --------------------------------------------------------------------------- #
# G-1：ORM 元数据列集合恰为 8 列；无 status / IP / MAC / 速率 / MTU / 载体列
# --------------------------------------------------------------------------- #
def test_g1_model_metadata_columns_exact():
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["network_interfaces"].columns}
    assert columns == NIC_TABLE_COLUMNS
    for token in FORBIDDEN_COLUMN_TOKENS:
        assert token not in columns, token


# --------------------------------------------------------------------------- #
# G-2：CHECK 集合恰为两个；取值集合逐字匹配 R-NIC-001 / R-NIC-002
# --------------------------------------------------------------------------- #
def test_g2_check_constraints_exact():
    from sqlalchemy import CheckConstraint

    from app.db.base import Base

    table = Base.metadata.tables["network_interfaces"]
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert set(checks) == {
        "ck_network_interfaces_technology_type",
        "ck_network_interfaces_purpose",
    }
    for value in TECHNOLOGY_TYPE_VALUES:
        assert value in checks["ck_network_interfaces_technology_type"]
    for value in PURPOSE_VALUES:
        assert value in checks["ck_network_interfaces_purpose"]


def test_g2_validation_sets_match_domain_rules():
    assert TECHNOLOGY_TYPE_VALUES == frozenset({"Ethernet", "InfiniBand", "RoCE", "Other"})
    assert PURPOSE_VALUES == frozenset(
        {"BMC", "Management", "Business", "Compute", "Storage", "DataTransfer", "Other"}
    )


# --------------------------------------------------------------------------- #
# G-3：FK 恰为 fk_network_interfaces_bare_metal 且 RESTRICT；ix 存在
# --------------------------------------------------------------------------- #
def test_g3_model_fk_and_index():
    from app.db.base import Base

    table = Base.metadata.tables["network_interfaces"]
    fks = list(table.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.name == "fk_network_interfaces_bare_metal"
    assert fk.ondelete == "RESTRICT"
    assert fk.onupdate == "RESTRICT"
    assert fk.target_fullname == "bare_metals.id"

    index_names = {index.name for index in table.indexes}
    assert "ix_network_interfaces_bare_metal_id" in index_names


# --------------------------------------------------------------------------- #
# G-4：唯一索引集合为空；无名称唯一性预检
# --------------------------------------------------------------------------- #
def test_g4_no_unique_index_in_orm():
    from app.db.base import Base

    table = Base.metadata.tables["network_interfaces"]
    unique = [index.name for index in table.indexes if index.unique]
    assert unique == [], f"network_interfaces 不得有任何唯一索引：{unique}"
    assert not [index.name for index in table.indexes if (index.name or "").startswith("ux_")]


def test_g4_no_uniqueness_preflight_in_module_sources():
    offenders: list[str] = []
    for path, source in _nic_module_sources():
        for token in UNIQUENESS_PREFLIGHT_TOKENS:
            if token in source:
                offenders.append(f"{path}: {token}")
    assert offenders == [], f"NIC 模块不得实现名称唯一性预检：{offenders}"


# --------------------------------------------------------------------------- #
# G-5：表集合 guard 演进（network_interfaces / 0005）
# --------------------------------------------------------------------------- #
def test_g5_table_whitelist_includes_nic():
    from tests.database.test_schema import EXPECTED_TABLES

    assert "network_interfaces" in EXPECTED_TABLES


def test_g5_migration_head_is_0005():
    from tests.database.helpers import MIGRATION_HEAD

    assert MIGRATION_HEAD == "0005_f004_network_interfaces"


# --------------------------------------------------------------------------- #
# G-6：EXPECTED_GET_ROUTES 追加 NIC 两条 GET（只增不删）
# --------------------------------------------------------------------------- #
def test_g6_expected_get_routes_contains_nic_routes():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES

    assert "/api/network-interfaces" in EXPECTED_GET_ROUTES
    assert "/api/network-interfaces/{network_interface_id}" in EXPECTED_GET_ROUTES


# --------------------------------------------------------------------------- #
# G-7：BOUNDARY_TOKENS 移除 NIC token、保留其它、保持全局扫描
# --------------------------------------------------------------------------- #
def test_g7_boundary_tokens_narrowed_but_global():
    from tests import test_cluster_views_guards as cv

    tokens = cv.BOUNDARY_TOKENS
    assert "network-interface" not in tokens
    assert "network_interface" not in tokens
    for kept in ("ip-address", "ip_address", "container", "service"):
        assert kept in tokens

    # 全局扫描不得被收窄到单模块：guard 源码仍对**全部** OpenAPI path 扫描。
    source = (REPO_ROOT / "tests/test_cluster_views_guards.py").read_text(encoding="utf-8")
    assert '_openapi()["paths"]' in source
    assert 'for path in _openapi()["paths"]' in source


# --------------------------------------------------------------------------- #
# G-8：BARE_METAL_ACTIVE_CHILD_CHECKS 同时含 VM 与 NIC，且被删除路径真实消费
# --------------------------------------------------------------------------- #
def test_g8_bare_metal_checks_contain_both_vm_and_nic():
    from app.virtual_machines.deletion import has_active_virtual_machines

    assert isinstance(BARE_METAL_ACTIVE_CHILD_CHECKS, tuple)
    assert has_active_virtual_machines in BARE_METAL_ACTIVE_CHILD_CHECKS
    assert has_active_network_interfaces in BARE_METAL_ACTIVE_CHILD_CHECKS


def test_g8_bare_metal_delete_path_consumes_declared_checks():
    source = (REPO_ROOT / "backend/app/bare_metals/service.py").read_text(encoding="utf-8")
    assert "soft_delete(" in source
    assert "BARE_METAL_ACTIVE_CHILD_CHECKS" in _soft_delete_active_children_args(source)


# --------------------------------------------------------------------------- #
# G-9：NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS 显式声明 = () 且删除路径 AST 传入
# --------------------------------------------------------------------------- #
def test_g9_nic_active_child_checks_explicitly_declared():
    assert isinstance(NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS, tuple)
    assert NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS == ()
    source = (REPO_ROOT / "backend/app/network_interfaces/deletion.py").read_text(encoding="utf-8")
    assert "NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS" in source
    assert "= ()" in source, "必须显式声明空元组，而非隐式缺省"


def test_g9_nic_delete_path_passes_active_child_checks():
    source = (REPO_ROOT / "backend/app/network_interfaces/service.py").read_text(encoding="utf-8")
    assert "soft_delete(" in source, "NetworkInterface 删除必须委托统一软删服务"
    assert "NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS" in _soft_delete_active_children_args(source), (
        "必须通过 active_children= 关键字真实传入声明的活跃子检查（仅注释 / docstring 不算）"
    )


# --------------------------------------------------------------------------- #
# G-10：未定义约束「不实现」
# --------------------------------------------------------------------------- #
def test_g10_nic_schemas_have_no_undefined_constraints():
    from app.network_interfaces.schemas import NetworkInterfaceCreate, NetworkInterfaceUpdate

    for model in (NetworkInterfaceCreate, NetworkInterfaceUpdate):
        for field in model.model_fields:
            assert _field_constraint_flags(model, field) == set(), f"{model.__name__}.{field}"
        decorators = model.__pydantic_decorators__
        assert decorators.validators == {}
        assert decorators.field_validators == {}


def test_g10_no_undefined_checks_in_orm():
    from sqlalchemy import CheckConstraint

    from app.db.base import Base

    table = Base.metadata.tables["network_interfaces"]
    combined = " ".join(
        str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
    ).lower()
    for forbidden in ("length(", "trim(", "strpos(", "like", "collate"):
        assert forbidden not in combined, f"不得对字段施加未定义约束：{forbidden}"


# --------------------------------------------------------------------------- #
# G-11：无 CASCADE / COLLATE / 触发器（ORM 层）
# --------------------------------------------------------------------------- #
def test_g11_no_cascade_in_orm():
    from app.db.base import Base

    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.ondelete != "CASCADE", f"{table.name}.{fk.name}"


# --------------------------------------------------------------------------- #
# G-12：唯一软删写入路径 allow-list；NIC 模块不写 deleted_at
# --------------------------------------------------------------------------- #
def test_g12_deleted_at_writer_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


def test_g12_nic_module_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "network_interfaces") == {}


# --------------------------------------------------------------------------- #
# G-13：无通用 resources 表 / EAV / STI / 多态 / JSON(B)
# --------------------------------------------------------------------------- #
def test_g13_no_generic_eav_json_or_polymorphic():
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import configure_mappers

    from app.db.base import Base

    table = Base.metadata.tables["network_interfaces"]
    for column in table.columns:
        assert not isinstance(column.type, (JSON, JSONB)), column.name
    assert table.name not in ("resources",)
    assert "resource" not in table.name

    configure_mappers()
    offenders = [m.class_.__name__ for m in Base.registry.mappers if m.polymorphic_on is not None]
    assert offenders == []
    inherits = [m.class_.__name__ for m in Base.registry.mappers if m.inherits is not None]
    assert inherits == []


# --------------------------------------------------------------------------- #
# G-14：路由交付面封闭（恰 5 个端点）
# --------------------------------------------------------------------------- #
def test_g14_nic_router_registers_exactly_five_endpoints():
    routes = {
        (method, route.path)
        for route in network_interfaces_router.routes
        for method in route.methods
    }
    assert routes == {
        ("POST", "/network-interfaces"),
        ("GET", "/network-interfaces"),
        ("GET", "/network-interfaces/{network_interface_id}"),
        ("PATCH", "/network-interfaces/{network_interface_id}"),
        ("DELETE", "/network-interfaces/{network_interface_id}"),
    }
