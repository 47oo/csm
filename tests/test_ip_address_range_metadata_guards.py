"""F022 IPAddressRange 元数据字段 guard（G-F022-1 ~ G-F022-9，可失败）。

把「9 字段封闭」「name / subnet_mask / vlan 语义边界」「唯一软删写入路径」「唯一 IPv4 /
掩码解析」「SQLSTATE 键集合不变」「不实现未确认能力（name 长度 / trim / 字符集、掩码
自洽、VLAN 唯一、CIDR / IPv6 / 网关 / DHCP / DNS / 使用率）」变成会失败的测试，而非
口头约定（``docs/architecture/f022-network-segment-metadata-handoff.md`` Test Work /
Database Handoff V-31 ~ V-34）。
"""

from __future__ import annotations

import ast

from app.common.sqlstate import SQLSTATE_MAP
from app.ip_address_ranges.router import router as ip_address_ranges_router
from app.ip_address_ranges.schemas import (
    MUTABLE_FIELDS,
    IpAddressRangeCreate,
    IpAddressRangeRead,
    IpAddressRangeUpdate,
)
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
)

READ_FIELDS = {
    "id",
    "cluster_id",
    "start_ip",
    "end_ip",
    "name",
    "subnet_mask",
    "vlan",
    "created_at",
    "updated_at",
}

#: F022 不得新增的字段 / 概念（未确认即不实现，不承诺）。
FORBIDDEN_CONCEPTS = (
    "cidr",
    "prefix_length",
    "network_address",
    "broadcast_address",
    "gateway",
    "dhcp",
    "dns",
    "ipv6",
    "utilization",
    "capacity",
    "usage",
    "assigned_to",
    "assigned_at",
    "reclaimed_at",
    "description",
    "purpose",
)

MIGRATION_PATH = (
    REPO_ROOT / "backend" / "migrations" / "versions" / "0010_f022_ip_range_metadata.py"
)

#: F021 既有 SQLSTATE 键集合；F022 不得新增。
EXPECTED_SQLSTATE_KEYS = {"23502", "23514", "23505", "23503", "23P01"}

IPV4_OWNER = "backend/app/ip_address_ranges/ipv4.py"


def _module_sources():
    for path in sorted((APP_DIR / "ip_address_ranges").rglob("*.py")):
        yield str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8")


def _openapi() -> dict:
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


# --------------------------------------------------------------------------- #
# G-F022-1：请求 / 响应 schema 恰 9 字段；name 无长度 / pattern 约束
# --------------------------------------------------------------------------- #
def test_g_f022_1_schemas_closed_and_name_unconstrained():
    assert set(IpAddressRangeCreate.model_fields) == {
        "cluster_id",
        "start_ip",
        "end_ip",
        "name",
        "subnet_mask",
        "vlan",
    }
    assert set(IpAddressRangeUpdate.model_fields) == {
        "start_ip",
        "end_ip",
        "name",
        "subnet_mask",
        "vlan",
    }
    assert set(IpAddressRangeRead.model_fields) == READ_FIELDS
    assert MUTABLE_FIELDS == ("start_ip", "end_ip", "name", "subnet_mask", "vlan")

    # name / subnet_mask 未定义长度 / trim / 空串 / 字符集约束（不实现、不承诺）。
    for model in (IpAddressRangeCreate, IpAddressRangeUpdate):
        assert model.model_fields["name"].metadata == []
        assert model.model_fields["subnet_mask"].metadata == []
    # vlan 用 StrictInt（拒绝 bool / float / str），且无额外范围约束在 schema 层。
    assert IpAddressRangeCreate.model_fields["vlan"].metadata == []

    for token in FORBIDDEN_CONCEPTS:
        assert token not in READ_FIELDS, token


# --------------------------------------------------------------------------- #
# G-F022-2：响应字段集合恰 9（OpenAPI）；无第二维度查询参数 / 端点
# --------------------------------------------------------------------------- #
def test_g_f022_2_openapi_surface_closed():
    spec = _openapi()
    read_props = spec["components"]["schemas"]["IpAddressRangeRead"]["properties"]
    assert set(read_props) == READ_FIELDS

    list_op = spec["paths"]["/api/ip-address-ranges"]["get"]
    names = {p.get("name") for p in list_op.get("parameters", [])}
    assert names == {"page", "page_size", "cluster_id"}

    range_paths = [p for p in spec["paths"] if p.startswith("/api/ip-address-ranges")]
    for path in range_paths:
        lowered = path.lower()
        for token in (*FORBIDDEN_CONCEPTS, "by-name", "filter", "sort", "gateway"):
            assert token not in lowered, (path, token)


# --------------------------------------------------------------------------- #
# G-F022-3：路由端点仍恰 5 个（无新增）
# --------------------------------------------------------------------------- #
def test_g_f022_3_router_endpoints_unchanged():
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


# --------------------------------------------------------------------------- #
# G-F022-4：唯一软删写入路径仍为 deletion/service.py；模块内零 deleted_at 赋值
# --------------------------------------------------------------------------- #
def test_g_f022_4_single_deleted_at_writer():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, writers
    assert scan_deleted_at_writes(APP_DIR / "ip_address_ranges") == {}


# --------------------------------------------------------------------------- #
# G-F022-5：唯一 IPv4 / 掩码解析实现仍只在 ipv4.py（不复制第二份）
# --------------------------------------------------------------------------- #
def test_g_f022_5_single_ipv4_and_mask_parser():
    definitions: list[tuple[str, str]] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        relpath = str(path.relative_to(REPO_ROOT))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name in (
                "parse_ipv4",
                "format_ipv4",
                "extract_ipv4_for_guard",
                "parse_subnet_mask",
            ):
                definitions.append((relpath, node.name))
    assert {relpath for relpath, _ in definitions} == {IPV4_OWNER}, definitions
    assert {name for _, name in definitions} == {
        "parse_ipv4",
        "format_ipv4",
        "extract_ipv4_for_guard",
        "parse_subnet_mask",
    }


def test_g_f022_5_service_reuses_mask_function():
    source = (APP_DIR / "ip_address_ranges" / "service.py").read_text(encoding="utf-8")
    assert "parse_subnet_mask" in source
    assert "def parse_subnet_mask" not in source
    # 不引入标准库 ipaddress 作为第二份解析 / IPv6 入口。
    assert "import ipaddress" not in source


# --------------------------------------------------------------------------- #
# G-F022-6：SQLSTATE 键集合不变；23505 → 409 CONFLICT / DUPLICATE
# --------------------------------------------------------------------------- #
def test_g_f022_6_sqlstate_map_unchanged():
    assert set(SQLSTATE_MAP) == EXPECTED_SQLSTATE_KEYS
    duplicate = SQLSTATE_MAP["23505"]
    assert duplicate.status_code == 409
    assert duplicate.error_code == "CONFLICT"
    assert duplicate.detail_code == "DUPLICATE"


# --------------------------------------------------------------------------- #
# G-F022-7：ORM partial unique index 声明正确（含谓词，无 COLLATE / lower）
# --------------------------------------------------------------------------- #
def test_g_f022_7_orm_partial_unique_index():
    from app.db.base import Base

    table = Base.metadata.tables["ip_address_ranges"]
    index = next(
        i for i in table.indexes if i.name == "ux_ip_address_ranges_cluster_name_active"
    )
    assert index.unique is True
    assert [c.name for c in index.columns] == ["cluster_id", "name"]
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert "deleted_at IS NULL" in predicate
    assert "name IS NOT NULL" in predicate
    assert "COLLATE" not in predicate and "lower(" not in predicate


# --------------------------------------------------------------------------- #
# G-F022-8：migration 0010 静态形态（列 / partial unique / CHECK / 无回填 / 逆序）
# --------------------------------------------------------------------------- #
def test_g_f022_8_migration_static_shape():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "0010_f022_ip_range_metadata"' in source
    assert 'down_revision: str | None = "0009_f020_ip_address_ranges"' in source
    upgrade_body = source.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    downgrade = source.split("def downgrade()", 1)[1]

    for column in ('"name"', '"subnet_mask"', '"vlan"'):
        assert column in upgrade_body, column
    assert "sa.Text()" in upgrade_body and "sa.Integer()" in upgrade_body
    assert "ux_ip_address_ranges_cluster_name_active" in upgrade_body
    assert "deleted_at IS NULL AND name IS NOT NULL" in upgrade_body
    assert "vlan BETWEEN 1 AND 4094" in upgrade_body
    # 无 server_default / 无回填 / 无 COLLATE / 无 lower() / 无 CASCADE / 无触发器。
    assert "server_default=" not in upgrade_body
    assert "COLLATE" not in upgrade_body
    assert "lower(" not in upgrade_body
    assert "CASCADE" not in upgrade_body
    assert "CREATE TRIGGER" not in upgrade_body.upper()

    # downgrade 严格逆序：drop index → drop constraint → drop vlan → subnet_mask → name。
    assert downgrade.index("drop_index") < downgrade.index("drop_constraint")
    assert downgrade.index("drop_constraint") < downgrade.index('"vlan"')
    assert downgrade.index('"vlan"') < downgrade.index('"subnet_mask"')
    assert downgrade.index('"subnet_mask"') < downgrade.index('"name"')


# --------------------------------------------------------------------------- #
# G-F022-9：不实现未确认能力（name 校验 / 掩码自洽 / VLAN 唯一 / 额外字段）
# --------------------------------------------------------------------------- #
def test_g_f022_9_no_name_trim_or_charset_validation():
    for relpath, source in _module_sources():
        assert ".strip(" not in source, relpath
        assert "casefold(" not in source, relpath
        assert "isalnum(" not in source, relpath
        assert "isalpha(" not in source, relpath


def test_g_f022_9_no_vlan_uniqueness():
    from sqlalchemy import UniqueConstraint

    from app.db.base import Base

    table = Base.metadata.tables["ip_address_ranges"]
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            raise AssertionError(f"不得新增 VLAN / 其它唯一约束：{constraint.name}")
    unique_indexes = {i.name for i in table.indexes if i.unique}
    assert unique_indexes == {"ux_ip_address_ranges_cluster_name_active"}


def test_g_f022_9_no_mask_self_consistency_check():
    # 掩码为描述性元数据：service 不得将 mask 与 start / end 做自洽比较。
    source = (APP_DIR / "ip_address_ranges" / "service.py").read_text(encoding="utf-8")
    for token in ("netmask", "network_address", "broadcast_address", "ip_network", "prefixlen"):
        assert token not in source, token
