"""F020 IPAddressRange 静态 / 结构 guard（G-F020-1 ~ G-F020-10）。

把「列集合封闭」「无状态 / 无 CIDR / 无分配」「唯一软删写入路径」「删除守卫接线」
「路由交付面封闭」「SQLSTATE 单一映射」「ip_address 自由文本不变」变成会失败的测试，
而非口头约定（``docs/architecture/f020-ip-address-range-handoff.md`` Test Work）。
"""

from __future__ import annotations

import ast

from app.clusters.deletion import CLUSTER_ACTIVE_CHILD_CHECKS
from app.common.sqlstate import SQLSTATE_MAP
from app.ip_address_ranges.deletion import (
    IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS,
    has_active_ip_address_ranges,
)
from app.ip_address_ranges.router import router as ip_address_ranges_router
from app.ip_address_ranges.schemas import MUTABLE_FIELDS
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
)

READ_FIELDS = {"id", "cluster_id", "start_ip", "end_ip", "created_at", "updated_at"}
TABLE_COLUMNS = {*READ_FIELDS, "deleted_at"}

FORBIDDEN_FIELD_TOKENS = (
    "status",
    "state",
    "name",
    "description",
    "purpose",
    "cidr",
    "prefix_length",
    "network_address",
    "broadcast_address",
    "gateway",
    "vlan",
    "dhcp",
    "dns",
    "capacity",
    "utilization",
    "assigned_at",
    "reclaimed_at",
    "assigned_to",
    "owner",
    "pool",
)


def _openapi() -> dict:
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


def _module_sources(subdir: str) -> list[tuple[str, str]]:
    return [
        (str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8"))
        for path in sorted((APP_DIR / subdir).rglob("*.py"))
    ]


# --------------------------------------------------------------------------- #
# G-F020-1：ORM / 表列集合恰为 7 列；无状态 / CIDR / 分配类列
# --------------------------------------------------------------------------- #
def test_g_f020_1_model_metadata_columns_exact():
    from app.db.base import Base

    table = Base.metadata.tables["ip_address_ranges"]
    assert {column.name for column in table.columns} == TABLE_COLUMNS
    for token in FORBIDDEN_FIELD_TOKENS:
        assert token not in TABLE_COLUMNS, token


def test_g_f020_1_constraints_and_indexes_exact():
    from sqlalchemy import CheckConstraint
    from sqlalchemy.dialects.postgresql import ExcludeConstraint

    from app.db.base import Base

    table = Base.metadata.tables["ip_address_ranges"]
    assert table.primary_key.name == "pk_ip_address_ranges"
    checks = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks == ["ck_ip_address_ranges_bounds"]
    excludes = [c.name for c in table.constraints if isinstance(c, ExcludeConstraint)]
    assert excludes == ["ex_ip_address_ranges_active_no_overlap"]
    assert {index.name for index in table.indexes} == {"ix_ip_address_ranges_cluster_id"}

    fks = list(table.foreign_keys)
    assert len(fks) == 1
    assert fks[0].name == "fk_ip_address_ranges_cluster"
    assert fks[0].ondelete == "RESTRICT" and fks[0].onupdate == "RESTRICT"


def test_g_f020_1_start_end_are_bigint():
    from sqlalchemy import BigInteger

    from app.db.base import Base

    table = Base.metadata.tables["ip_address_ranges"]
    assert isinstance(table.columns["start_ip"].type, BigInteger)
    assert isinstance(table.columns["end_ip"].type, BigInteger)


# --------------------------------------------------------------------------- #
# G-F020-2：请求 / 响应 schema 封闭；PATCH 可变字段恰为 start/end
# --------------------------------------------------------------------------- #
def test_g_f020_2_schemas_are_closed():
    from app.ip_address_ranges.schemas import (
        IpAddressRangeCreate,
        IpAddressRangeRead,
        IpAddressRangeUpdate,
    )

    assert MUTABLE_FIELDS == ("start_ip", "end_ip")
    assert set(IpAddressRangeCreate.model_fields) == {"cluster_id", "start_ip", "end_ip"}
    assert set(IpAddressRangeUpdate.model_fields) == {"start_ip", "end_ip"}
    assert set(IpAddressRangeRead.model_fields) == READ_FIELDS
    for model in (IpAddressRangeCreate, IpAddressRangeUpdate, IpAddressRangeRead):
        assert model.model_config.get("extra") == "forbid" or model is IpAddressRangeRead
    read_schema = _openapi()["components"]["schemas"]["IpAddressRangeRead"]["properties"]
    assert set(read_schema) == READ_FIELDS


# --------------------------------------------------------------------------- #
# G-F020-3：路由交付面恰 5 个端点；query 参数封闭
# --------------------------------------------------------------------------- #
def test_g_f020_3_router_registers_exactly_five_endpoints():
    routes = {
        (method, route.path)
        for route in ip_address_ranges_router.routes
        for method in route.methods
    }
    assert routes == {
        ("POST", "/ip-address-ranges"),
        ("GET", "/ip-address-ranges"),
        ("GET", "/ip-address-ranges/{ip_address_range_id}"),
        ("PATCH", "/ip-address-ranges/{ip_address_range_id}"),
        ("DELETE", "/ip-address-ranges/{ip_address_range_id}"),
    }


def test_g_f020_3_list_query_params_are_closed():
    op = _openapi()["paths"]["/api/ip-address-ranges"]["get"]
    names = {p.get("name") for p in op.get("parameters", [])}
    assert names == {"page", "page_size", "cluster_id"}


def test_g_f020_3_no_out_of_scope_routes():
    forbidden = (
        "by-name",
        "restore",
        "undelete",
        "purge",
        "trash",
        "batch",
        "deleted",
        "allocate",
        "assign",
        "usage",
    )
    offenders = [
        path
        for path in _openapi()["paths"]
        if path.startswith("/api/ip-address-ranges")
        and any(token in path.lower() for token in forbidden)
    ]
    assert offenders == [], f"不存在越界范围段端点：{offenders}"


# --------------------------------------------------------------------------- #
# G-F020-4：唯一软删写入路径仍为 deletion/service.py；模块内零 deleted_at 赋值
# --------------------------------------------------------------------------- #
def test_g_f020_4_global_deleted_at_writer_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


def test_g_f020_4_range_module_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "ip_address_ranges") == {}


def test_g_f020_4_delete_consumes_declared_checks():
    source = (APP_DIR / "ip_address_ranges" / "service.py").read_text(encoding="utf-8")
    values: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            callee = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if callee == "soft_delete":
                for keyword in node.keywords:
                    if keyword.arg == "active_children":
                        values.append(ast.unparse(keyword.value))
    assert values == ["IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS"]


# --------------------------------------------------------------------------- #
# G-F020-5：删除守卫接线（Cluster + 范围段自身）
# --------------------------------------------------------------------------- #
def test_g_f020_5_child_checks_wired():
    from app.ip_address_ranges.deletion import has_active_ip_addresses_in_range

    assert IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS == (has_active_ip_addresses_in_range,)
    assert has_active_ip_address_ranges in CLUSTER_ACTIVE_CHILD_CHECKS


# --------------------------------------------------------------------------- #
# G-F020-6：SQLSTATE 23P01 → 409 CONFLICT / OVERLAP（单一映射表，additive）
# --------------------------------------------------------------------------- #
def test_g_f020_6_sqlstate_mapping():
    mapping = SQLSTATE_MAP["23P01"]
    assert mapping.status_code == 409
    assert mapping.error_code == "CONFLICT"
    assert mapping.detail_code == "OVERLAP"
    for code in ("23502", "23514", "23505", "23503"):
        assert code in SQLSTATE_MAP, "既有映射不得被删除"


# --------------------------------------------------------------------------- #
# G-F020-7：IPv4 纯函数语义（规范化 / 严格 / 守卫解析）
# --------------------------------------------------------------------------- #
def test_g_f020_7_ipv4_pure_functions():
    from app.ip_address_ranges.ipv4 import (
        extract_ipv4_for_guard,
        format_ipv4,
        parse_ipv4,
    )

    assert parse_ipv4("010.000.000.001") == parse_ipv4("10.0.0.1") == 167772161
    assert format_ipv4(167772161) == "10.0.0.1"
    assert format_ipv4(parse_ipv4("255.255.255.255")) == "255.255.255.255"
    for bad in ("10.0.0.256", "10.0.0", "abc", "1.2.3.4/24", "2001:db8::1", "", " 10.0.0.1"):
        try:
            parse_ipv4(bad)
        except ValueError:
            continue
        raise AssertionError(f"parse_ipv4 必须拒绝 {bad!r}")
    assert extract_ipv4_for_guard("10.0.1.1/16") == parse_ipv4("10.0.1.1")
    assert extract_ipv4_for_guard("abc") is None
    assert extract_ipv4_for_guard("") is None
    assert extract_ipv4_for_guard(" 10.0.1.1") is None


# --------------------------------------------------------------------------- #
# G-F020-8：ip_address 自由文本立场不变（无 F020 耦合 / 无新增校验）
# --------------------------------------------------------------------------- #
def test_g_f020_8_ip_addresses_module_does_not_use_range_ipv4_helpers():
    for relpath, source in _module_sources("ip_addresses"):
        assert "ip_address_ranges" not in source, relpath
        assert "parse_ipv4" not in source, relpath
        assert "extract_ipv4_for_guard" not in source, relpath


def test_g_f020_8_ip_address_column_has_no_format_constraint():
    from sqlalchemy import CheckConstraint, Text

    from app.db.base import Base

    table = Base.metadata.tables["ip_addresses"]
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks == [], "F020 不得给 ip_addresses 增加 CHECK"
    assert isinstance(table.columns["ip_address"].type, Text)


def test_g_f020_8_no_ip_address_writes_in_range_module():
    for relpath, source in _module_sources("ip_address_ranges"):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                callee = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                assert callee != "IpAddress", f"{relpath} 不得写入 ip_addresses"


# --------------------------------------------------------------------------- #
# G-F020-9：交付面 allow-list 与表白名单演进
# --------------------------------------------------------------------------- #
def test_g_f020_9_table_whitelist_and_prefix():
    from tests.database.test_schema import EXPECTED_TABLES
    from tests.test_structure_guard import APPROVED_API_PREFIXES

    assert "ip_address_ranges" in EXPECTED_TABLES
    assert "ip-address-ranges" in APPROVED_API_PREFIXES


# --------------------------------------------------------------------------- #
# G-F020-10：契约已落盘且 READY（AC-29）
# --------------------------------------------------------------------------- #
def test_g_f020_10_contract_ready():
    contract = REPO_ROOT / "docs" / "api" / "f020-ip-address-range.md"
    assert contract.exists(), "契约必须落盘"
    text = contract.read_text(encoding="utf-8")
    assert "Status: **READY**" in text
