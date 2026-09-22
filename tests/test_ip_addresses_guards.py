"""F005 IPAddress 静态 / 结构 guard（G-1 ~ G-17）。

把「列集合封闭」「无格式 / 归一化」「唯一软删写入路径」「``cluster_id`` 单一写入路径」
「无 VRF / 状态 / IP 池 / 多态父载体」「路由交付面封闭」「活跃子检查点演进且被消费」
变成会失败的测试，而非口头约定（``docs/architecture/f005-ip-address-handoff.md``）。
"""

from __future__ import annotations

import ast

from app.bare_metals.deletion import BARE_METAL_ACTIVE_CHILD_CHECKS
from app.clusters.deletion import CLUSTER_ACTIVE_CHILD_CHECKS
from app.ip_addresses.router import router as ip_addresses_router
from app.ip_addresses.schemas import MUTABLE_FIELDS
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
)

IP_ADDRESS_READ_FIELDS = {
    "id",
    "network_interface_id",
    "ip_address",
    "created_at",
    "updated_at",
}

IP_ADDRESS_TABLE_COLUMNS = {*IP_ADDRESS_READ_FIELDS, "deleted_at", "cluster_id"}

FORBIDDEN_CONSTRAINT_ATTRS = (
    "min_length",
    "max_length",
    "pattern",
    "strip_whitespace",
    "to_lower",
    "to_upper",
)

#: G-11：IP 资源上不得出现的未确认字段 token（列 / schema / OpenAPI 参数 / 端点）。
FORBIDDEN_FIELD_TOKENS = (
    "status",
    "vrf",
    "vrf_id",
    "tenant",
    "namespace",
    "netns",
    "vni",
    "pool",
    "pool_id",
    "subnet",
    "segment",
    "gateway",
    "vlan",
    "dhcp",
    "dns",
    "discovered",
    "external_id",
    "last_seen",
    "sync",
    "credential",
    "carrier_type",
    "owner_type",
    "parent_type",
    "bare_metal_id",
    "virtual_machine_id",
    "container_id",
    "service_id",
    "purpose",
    "note",
    "remark",
    "owner",
    "assigned_at",
    "reclaimed_at",
    "state",
    "description",
)

#: G-10：``app/ip_addresses/**`` 中不得出现的格式 / 归一化符号。
FORBIDDEN_FORMAT_SYMBOLS = (
    "ipaddress",
    "inet_pton",
    "inet_ntoa",
    "ip_network",
    "normalize",
    "strip",
    "split",
    "lower",
    "upper",
    "re",
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


def _module_sources(subdir: str) -> list[tuple[str, str]]:
    return [
        (str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8"))
        for path in sorted((APP_DIR / subdir).rglob("*.py"))
    ]


def _all_app_sources() -> list[tuple[str, str]]:
    return [
        (str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8"))
        for path in sorted(APP_DIR.rglob("*.py"))
    ]


def _enclosing_function(tree: ast.Module, node: ast.AST) -> str:
    names = []
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(candidate):
                if child is node:
                    names.append(candidate.name)
    return names[-1] if names else "<module>"


def _cluster_id_write_locations_in(relpath: str, source: str) -> set[tuple[str, str]]:
    """G-9 断言 1（单文件）：向 ``IpAddress`` / ``ip_addresses`` 写 ``cluster_id`` 的位置。

    F005 REV-3 加固：原实现只盖 ``IpAddress(cluster_id=...)`` 构造、``setattr`` 与
    属性赋值三种形态，**漏掉** ``update(...).values(cluster_id=...)`` 等 ORM / 裸 SQL
    形态（评审已注入证实可绕过）。现一并覆盖：

    - 任何调用出现 ``cluster_id=`` **关键字实参**（含 ``.values(cluster_id=...)``）；
    - 任何调用中出现含 ``"cluster_id"`` 键的**字典字面量**（含 ``.values({...})``）；
    - ``text("... cluster_id ...")`` / ``execute("UPDATE ... cluster_id ...")`` 等
      含 ``cluster_id`` 字面量的**裸 SQL**。
    """
    found: set[tuple[str, str]] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if callee == "IpAddress" and any(kw.arg == "cluster_id" for kw in node.keywords):
                found.add((relpath, _enclosing_function(tree, node)))
            if callee == "setattr" and len(node.args) >= 2:
                second = node.args[1]
                if isinstance(second, ast.Constant) and second.value == "cluster_id":
                    found.add((relpath, _enclosing_function(tree, node)))
            # 形态 A：ORM 赋值形态——``.values(cluster_id=...)`` 或 ``dict(cluster_id=...)``。
            # 注意：**不得**写成「任何出现 cluster_id= 的调用」，那会把
            # ``list_active(params, cluster_id=...)`` 这类**过滤参数传递**误判为写入
            # （本仓库存在此类合法读取路径）。只认真正赋值列的 callee。
            if callee in {"values", "dict"} and any(kw.arg == "cluster_id" for kw in node.keywords):
                found.add((relpath, _enclosing_function(tree, node)))
            # 形态 B：字典字面量含 "cluster_id" 键（含 .values({"cluster_id": ...})）。
            for arg in node.args:
                if isinstance(arg, ast.Dict) and any(
                    isinstance(key, ast.Constant) and key.value == "cluster_id" for key in arg.keys
                ):
                    found.add((relpath, _enclosing_function(tree, node)))
            # 形态 C：裸 SQL 字面量含 cluster_id。
            if callee in {"text", "execute", "exec_driver_sql"}:
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and "cluster_id" in arg.value
                    ):
                        found.add((relpath, _enclosing_function(tree, node)))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "cluster_id":
                    found.add((relpath, _enclosing_function(tree, node)))
    return found


def _cluster_id_write_locations() -> set[tuple[str, str]]:
    """G-9 断言 1：向 ``IpAddress`` 实例 / ``ip_addresses`` 写 ``cluster_id`` 的位置。"""
    found: set[tuple[str, str]] = set()
    for relpath, source in _all_app_sources():
        found |= _cluster_id_write_locations_in(relpath, source)
    return found


def _cluster_chain_read_locations() -> set[tuple[str, str]]:
    """G-9 断言 2：在 IP 模块内读取 ``BareMetal.cluster_id`` 用作推导的函数。"""
    found: set[tuple[str, str]] = set()
    for relpath, source in _module_sources("ip_addresses"):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "cluster_id"
                and isinstance(node.value, ast.Name)
                and node.value.id == "BareMetal"
            ):
                found.add((relpath, _enclosing_function(tree, node)))
    return found


def _derive_cluster_id_call_locations() -> set[tuple[str, str]]:
    """G-9 断言 3：``derive_cluster_id`` 的调用点（定义不算）。"""
    found: set[tuple[str, str]] = set()
    for relpath, source in _all_app_sources():
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if callee == "derive_cluster_id":
                    found.add((relpath, _enclosing_function(tree, node)))
    return found


def _openapi() -> dict:
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


# --------------------------------------------------------------------------- #
# G-1：ORM 元数据列集合恰为 7 列；无 status / VRF / 池 / DHCP / DNS / 载体 / 备注列
# --------------------------------------------------------------------------- #
def test_g1_model_metadata_columns_exact():
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["ip_addresses"].columns}
    assert columns == IP_ADDRESS_TABLE_COLUMNS
    for token in FORBIDDEN_FIELD_TOKENS:
        assert token not in columns, token


# --------------------------------------------------------------------------- #
# G-2：CHECK 集合为空；ip_address 为 TEXT 且无长度
# --------------------------------------------------------------------------- #
def test_g2_check_set_is_empty():
    from sqlalchemy import CheckConstraint

    from app.db.base import Base

    table = Base.metadata.tables["ip_addresses"]
    checks = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks == [], f"ip_addresses 不得有任何 CHECK 约束：{checks}"


def test_g2_ip_address_is_text_without_length():
    from sqlalchemy import Text

    from app.db.base import Base

    column = Base.metadata.tables["ip_addresses"].columns["ip_address"]
    assert isinstance(column.type, Text)
    assert getattr(column.type, "length", None) is None


# --------------------------------------------------------------------------- #
# G-3：PK 恰为 pk_ip_addresses；FK 恰为 2 条 RESTRICT / RESTRICT
# --------------------------------------------------------------------------- #
def test_g3_primary_key_and_foreign_keys_exact():
    from app.db.base import Base

    table = Base.metadata.tables["ip_addresses"]
    assert table.primary_key.name == "pk_ip_addresses"

    fks = {fk.name: fk for fk in table.foreign_keys}
    assert set(fks) == {
        "fk_ip_addresses_network_interface",
        "fk_ip_addresses_cluster",
    }
    assert fks["fk_ip_addresses_network_interface"].target_fullname == "network_interfaces.id"
    assert fks["fk_ip_addresses_cluster"].target_fullname == "clusters.id"
    for fk in fks.values():
        assert fk.ondelete == "RESTRICT"
        assert fk.onupdate == "RESTRICT"


# --------------------------------------------------------------------------- #
# G-4：唯一索引集合恰为 {ux_ip_addresses_cluster_ip_active}，列序 / predicate 精确；
#      无 COLLATE / 无 lower()；另两个普通索引存在
# --------------------------------------------------------------------------- #
def test_g4_unique_index_exact_and_predicate():
    from app.db.base import Base

    table = Base.metadata.tables["ip_addresses"]
    unique = {index.name: index for index in table.indexes if index.unique}
    assert set(unique) == {"ux_ip_addresses_cluster_ip_active"}
    index = unique["ux_ip_addresses_cluster_ip_active"]
    assert [column.name for column in index.columns] == ["cluster_id", "ip_address"]
    where = index.dialect_options["postgresql"].get("where")
    assert where is not None
    assert "deleted_at IS NULL" in str(where)
    assert "COLLATE" not in str(where).upper()
    assert "lower(" not in str(where).lower()


def test_g4_other_indexes_exist_and_no_collate():
    from app.db.base import Base

    table = Base.metadata.tables["ip_addresses"]
    names = {index.name for index in table.indexes}
    assert "ix_ip_addresses_cluster_id" in names
    assert "ix_ip_addresses_network_interface_id" in names
    for index in table.indexes:
        assert "COLLATE" not in str(index).upper()
        for column in index.columns:
            assert getattr(column.type, "collation", None) is None, column.name


# --------------------------------------------------------------------------- #
# G-5：表集合 guard 演进（ip_addresses / 0006）
# --------------------------------------------------------------------------- #
def test_g5_table_whitelist_includes_ip_addresses():
    from tests.database.test_schema import EXPECTED_TABLES

    assert "ip_addresses" in EXPECTED_TABLES


def test_g5_migration_head_is_current():
    # F022 演进：head 从 0009 → 0010（不得删除本 guard，只更新当前 head）。
    from tests.database.helpers import MIGRATION_HEAD

    assert MIGRATION_HEAD == "0010_f022_ip_range_metadata"


# --------------------------------------------------------------------------- #
# G-6：EXPECTED_GET_ROUTES 追加两条 IP GET（只增不删）
# --------------------------------------------------------------------------- #
def test_g6_expected_get_routes_contains_ip_routes():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES

    assert "/api/ip-addresses" in EXPECTED_GET_ROUTES
    assert "/api/ip-addresses/{ip_address_id}" in EXPECTED_GET_ROUTES
    # 既有成员全部保留。
    for kept in (
        "/api/health",
        "/api/clusters",
        "/api/bare-metals",
        "/api/network-interfaces",
    ):
        assert kept in EXPECTED_GET_ROUTES


# --------------------------------------------------------------------------- #
# G-7：BOUNDARY_TOKENS 收窄（移除两个 ip token）、保留 service、全局扫描
# --------------------------------------------------------------------------- #
def test_g7_boundary_tokens_narrowed_but_global():
    from tests import test_cluster_views_guards as cv

    tokens = cv.BOUNDARY_TOKENS
    assert "ip-address" not in tokens
    assert "ip_address" not in tokens
    # F007 演进：Container 已成为合法资源（``/api/containers``），故**仅移除**
    # ``container``；``service`` 仍在集合中，且扫描仍为全局。
    # F008 演进：Service 已成为合法资源（``/api/services``），故**仅移除** ``service``。
    assert "container" not in tokens
    assert "service" not in tokens

    source = (REPO_ROOT / "tests/test_cluster_views_guards.py").read_text(encoding="utf-8")
    assert '_openapi()["paths"]' in source
    assert 'for path in _openapi()["paths"]' in source


# --------------------------------------------------------------------------- #
# G-8：F014 接线 —— NIC 检查非空含 IP；BM / Cluster 检查未被削弱；IP 检查显式空
# --------------------------------------------------------------------------- #
def test_g8_nic_checks_evolved_and_real():
    from app.ip_addresses.deletion import has_active_ip_addresses
    from app.network_interfaces.deletion import (
        NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS,
        has_active_network_interfaces,
    )
    from app.virtual_machines.deletion import has_active_virtual_machines

    assert isinstance(NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS, tuple)
    assert NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS
    assert has_active_ip_addresses in NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS

    # BareMetal 检查必须仍含 VM + NIC（不得被替换 / 削弱）。
    assert has_active_virtual_machines in BARE_METAL_ACTIVE_CHILD_CHECKS
    assert has_active_network_interfaces in BARE_METAL_ACTIVE_CHILD_CHECKS

    # Cluster 检查未被削弱：F002 的 BareMetal 检查保留，F020 追加范围段检查。
    from app.bare_metals.deletion import has_active_bare_metals
    from app.ip_address_ranges.deletion import has_active_ip_address_ranges

    assert has_active_bare_metals in CLUSTER_ACTIVE_CHILD_CHECKS
    assert has_active_ip_address_ranges in CLUSTER_ACTIVE_CHILD_CHECKS


def test_g8_ip_address_checks_explicitly_empty_and_consumed():
    from app.ip_addresses.deletion import IP_ADDRESS_ACTIVE_CHILD_CHECKS

    assert isinstance(IP_ADDRESS_ACTIVE_CHILD_CHECKS, tuple)
    assert IP_ADDRESS_ACTIVE_CHILD_CHECKS == ()
    source = (REPO_ROOT / "backend/app/ip_addresses/deletion.py").read_text(encoding="utf-8")
    assert "IP_ADDRESS_ACTIVE_CHILD_CHECKS" in source
    assert "= ()" in source, "必须显式声明空元组，而非隐式缺省"

    # AST：IP 删除路径必须真实消费该常量。
    service = (REPO_ROOT / "backend/app/ip_addresses/service.py").read_text(encoding="utf-8")
    assert "soft_delete(" in service
    assert "IP_ADDRESS_ACTIVE_CHILD_CHECKS" in _soft_delete_active_children_args(service)


def _soft_delete_active_children_args(source: str) -> list[str]:
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


def test_g8_nic_delete_path_consumes_declared_checks():
    source = (REPO_ROOT / "backend/app/network_interfaces/service.py").read_text(encoding="utf-8")
    assert "NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS" in _soft_delete_active_children_args(source)


# --------------------------------------------------------------------------- #
# G-9：cluster_id 单一写入路径（4 条断言）
# --------------------------------------------------------------------------- #
def test_g9_cluster_id_write_path_is_unique():
    assert _cluster_id_write_locations() == {("backend/app/ip_addresses/repository.py", "create")}


def test_g9_detector_covers_orm_and_raw_sql_write_forms():
    """F005 REV-3 回归：检测器必须盖住 ORM / 裸 SQL 写入形态。

    评审注入 ``update(IpAddress).values(cluster_id=...)`` 时原检测器**不失败**
    （G-9 仍 PASS），即单一写入路径 guard 存在可绕过的缺口。本测试以合成源码固定
    各形态均被检出，使「检测器覆盖范围」本身可被反驳。
    """
    stmt = "update(IpAddress).where(IpAddress.id == 1)"
    source = "\n".join(
        [
            "def probe():\n",
            f"    session.execute({stmt}.values(cluster_id=2))\n",
            f"    session.execute({stmt}.values({{'cluster_id': 2}}))\n",
            f"    session.execute({stmt}.values(dict(cluster_id=2)))\n",
            "    session.execute(text('UPDATE ip_addresses SET cluster_id = 2'))\n",
            "    session.execute('UPDATE ip_addresses SET cluster_id = 2')\n",
            "    row.cluster_id = 2\n",
            "    setattr(row, 'cluster_id', 2)\n",
            "    IpAddress(cluster_id=2)\n",
        ]
    )
    locations = _cluster_id_write_locations_in("synthetic/probe.py", source)
    assert locations == {("synthetic/probe.py", "probe")}, locations


def test_g9_cluster_chain_read_is_unique():
    assert _cluster_chain_read_locations() == {
        ("backend/app/ip_addresses/derivation.py", "derive_cluster_id")
    }


def test_g9_derive_cluster_id_call_is_unique():
    # F021 演进：新增两个只读推导调用点（`allocate_ip_auto` / `allocate_ip_manual`）；
    # `cluster_id` **写入**路径仍唯一（见 test_g9_cluster_id_write_path_is_unique）。
    # 断言按完整新集合精确演进，不得放宽为子集 / 包含式。
    assert _derive_cluster_id_call_locations() == {
        ("backend/app/ip_addresses/service.py", "create_ip_address"),
        ("backend/app/ip_allocations/service.py", "allocate_ip_auto"),
        ("backend/app/ip_allocations/service.py", "allocate_ip_manual"),
    }


def _code_identifiers(source: str) -> set[str]:
    """收集源码中的**代码标识符**（Name / Attribute / 关键字参数），忽略 docstring。"""
    identifiers: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.Call):
            identifiers.update(kw.arg for kw in node.keywords if kw.arg)
    return identifiers


def test_g9_cluster_id_absent_from_schemas_router_and_frontend():
    for relpath, source in _module_sources("ip_addresses"):
        if relpath.endswith(("schemas.py", "router.py")):
            assert "cluster_id" not in _code_identifiers(source), (
                f"{relpath} 不得出现 cluster_id（docstring 中的否定说明不算）"
            )

    read_schema = _openapi()["components"]["schemas"]["IpAddressRead"]["properties"]
    assert "cluster_id" not in read_schema
    assert set(read_schema) == IP_ADDRESS_READ_FIELDS

    frontend_client = REPO_ROOT / "frontend" / "src" / "api" / "ipAddresses.ts"
    if frontend_client.exists():
        assert "cluster_id" not in frontend_client.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# G-10：不实现格式 / 归一化 —— 源码无符号；schema 无约束元数据与 validator
# --------------------------------------------------------------------------- #
def test_g10_no_format_or_normalization_symbols_in_module():
    offenders: list[str] = []
    for relpath, source in _module_sources("ip_addresses"):
        names: set[str] = set()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
        for token in FORBIDDEN_FORMAT_SYMBOLS:
            if token in names:
                offenders.append(f"{relpath}: {token}")
    assert offenders == [], f"IP 模块不得做格式 / 归一化处理：{offenders}"


def test_g10_schemas_have_no_undefined_constraints_or_validators():
    from app.ip_addresses.schemas import IpAddressCreate, IpAddressRead, IpAddressUpdate

    for model in (IpAddressCreate, IpAddressUpdate, IpAddressRead):
        for field in model.model_fields:
            assert _field_constraint_flags(model, field) == set(), f"{model.__name__}.{field}"
        decorators = model.__pydantic_decorators__
        assert decorators.validators == {}
        assert decorators.field_validators == {}


# --------------------------------------------------------------------------- #
# G-11：无 status / VRF / 命名空间 / IP 池 / DHCP / DNS / 自动发现 / 多态父载体
# --------------------------------------------------------------------------- #
def test_g11_no_forbidden_tokens_in_schemas_and_openapi():
    from app.db.base import Base
    from app.ip_addresses.schemas import IpAddressCreate, IpAddressRead, IpAddressUpdate

    columns = {column.name for column in Base.metadata.tables["ip_addresses"].columns}
    for token in FORBIDDEN_FIELD_TOKENS:
        assert token not in columns, f"列 {token}"

    for model in (IpAddressCreate, IpAddressUpdate, IpAddressRead):
        for token in FORBIDDEN_FIELD_TOKENS:
            assert token not in model.model_fields, f"{model.__name__}.{token}"

    spec = _openapi()
    for path, operations in spec["paths"].items():
        if not path.startswith("/api/ip-addresses"):
            continue
        assert not any(token in path.lower() for token in FORBIDDEN_FIELD_TOKENS), path
        for operation in operations.values():
            names = {p.get("name") for p in operation.get("parameters", [])}
            for name in names:
                assert not any(token in (name or "").lower() for token in FORBIDDEN_FIELD_TOKENS)


# --------------------------------------------------------------------------- #
# G-12：无 confdeltype='c'（ORM 侧）；无触发器由 DB guard 负责
# --------------------------------------------------------------------------- #
def test_g12_no_cascade_in_orm():
    from app.db.base import Base

    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.ondelete != "CASCADE", f"{table.name}.{fk.name}"


# --------------------------------------------------------------------------- #
# G-13：无通用 resources 表 / EAV / STI / 多态 mapper / JSON(B)；表集合恰为 7
# --------------------------------------------------------------------------- #
def test_g13_no_generic_eav_json_or_polymorphic():
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import configure_mappers

    from app.db.base import Base

    table = Base.metadata.tables["ip_addresses"]
    for column in table.columns:
        assert not isinstance(column.type, (JSON, JSONB)), column.name

    configure_mappers()
    offenders = [m.class_.__name__ for m in Base.registry.mappers if m.polymorphic_on is not None]
    assert offenders == []
    inherits = [m.class_.__name__ for m in Base.registry.mappers if m.inherits is not None]
    assert inherits == []

    assert set(Base.metadata.tables) == {
        "clusters",
        "users",
        "sessions",
        "bare_metals",
        "virtual_machines",
        "network_interfaces",
        "ip_addresses",
        # F007：Container 独立资源表。
        "containers",
        # F008：Service 资源表 + N:M 多态绑定关系表。
        "services",
        "service_carriers",
        # F020：IP 地址范围段（地址池）资源表。
        "ip_address_ranges",
    }


# --------------------------------------------------------------------------- #
# G-14：唯一软删写入路径 allow-list；IP 模块写入 deleted_at 为 0
# --------------------------------------------------------------------------- #
def test_g14_deleted_at_writer_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


def test_g14_ip_module_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "ip_addresses") == {}


# --------------------------------------------------------------------------- #
# G-15：交付面封闭（恰 5 个端点 / query 参数封闭 / 无越界 / 无反向导入）
# --------------------------------------------------------------------------- #
def test_g15_router_registers_exactly_five_endpoints():
    routes = {
        (method, route.path) for route in ip_addresses_router.routes for method in route.methods
    }
    assert routes == {
        ("POST", "/ip-addresses"),
        ("GET", "/ip-addresses"),
        ("GET", "/ip-addresses/{ip_address_id}"),
        ("PATCH", "/ip-addresses/{ip_address_id}"),
        ("DELETE", "/ip-addresses/{ip_address_id}"),
    }


def test_g15_list_query_params_are_closed():
    op = _openapi()["paths"]["/api/ip-addresses"]["get"]
    names = {p.get("name") for p in op.get("parameters", [])}
    assert names == {"page", "page_size", "network_interface_id"}


def test_g15_no_out_of_scope_ip_routes():
    forbidden = ("by-name", "restore", "undelete", "purge", "trash", "batch", "deleted")
    offenders = [
        path
        for path in _openapi()["paths"]
        if path.startswith("/api/ip-addresses") and any(t in path.lower() for t in forbidden)
    ]
    assert offenders == [], f"不存在越界 IP 端点：{offenders}"


def test_g15_ip_module_does_not_import_network_interfaces_module():
    for relpath, source in _module_sources("ip_addresses"):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.network_interfaces"), relpath
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.network_interfaces"), relpath


# --------------------------------------------------------------------------- #
# G-16：migration head（DB 应用 / 可重复 / 重建 / downgrade 由 tests/database 覆盖）
# --------------------------------------------------------------------------- #
def test_g16_migration_revision_chain():
    from tests.database.helpers import MIGRATION_HEAD

    # F022 演进：head 为 0010，其 down_revision 指向 0009。
    assert MIGRATION_HEAD == "0010_f022_ip_range_metadata"
    migration = (
        REPO_ROOT
        / "backend"
        / "migrations"
        / "versions"
        / "0010_f022_ip_range_metadata.py"
    )
    source = migration.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0009_f020_ip_address_ranges"' in source


# --------------------------------------------------------------------------- #
# G-17：前端字段封闭（前端不在本次 Backend 交付范围内时条件断言）
# --------------------------------------------------------------------------- #
def test_g17_frontend_ip_client_is_closed_when_present():
    frontend_client = REPO_ROOT / "frontend" / "src" / "api" / "ipAddresses.ts"
    if not frontend_client.exists():
        # 本 Feature 的 Backend 层交付不含前端文件；前端落地后本断言自动激活。
        # 明确断言此刻确无 IP 前端客户端，避免「半成品」被静默放过。
        matches = list((REPO_ROOT / "frontend" / "src").rglob("*IpAddress*"))
        assert matches == [], f"存在未完成的 IP 前端文件：{matches}"
        return
    source = frontend_client.read_text(encoding="utf-8")
    assert "cluster_id" not in source
    for token in ("strip", "lower", "upper", "normalize", "isValidIp", "validateIp"):
        assert token not in source, f"前端 IP 客户端不得做格式 / 归一化 / 唯一性预检：{token}"


def test_g17_schema_mutable_fields_closed():
    from app.ip_addresses.schemas import IpAddressCreate, IpAddressUpdate

    assert MUTABLE_FIELDS == ("ip_address",)
    assert set(IpAddressCreate.model_config) >= {"extra"}
    assert IpAddressCreate.model_config.get("extra") == "forbid"
    assert IpAddressUpdate.model_config.get("extra") == "forbid"
    assert set(IpAddressCreate.model_fields) == {"network_interface_id", "ip_address"}
    assert set(IpAddressUpdate.model_fields) == {"ip_address"}
