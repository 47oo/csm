"""F021 分配静态 / 结构 guard（G-F021-1 ~ G-F021-8）。

把「端点面恰 2」「请求 schema 封闭」「分配模块零 ``deleted_at`` 写入 / 零
``IpAddress(cluster_id=...)``」「复用 F005 单一 ``cluster_id`` 写入路径」「``SQLSTATE_MAP``
键集合不变」「migration head 仍 0009」「唯一一份 IPv4 解析器」变成会失败的测试，而非
口头约定（``docs/architecture/f021-ip-address-allocation-handoff.md`` Test Work）。
"""

from __future__ import annotations

import ast

from app.common.sqlstate import SQLSTATE_MAP
from app.ip_allocations.router import router as ip_allocations_router
from app.ip_allocations.schemas import (
    IpAddressAutoAllocateRequest,
    IpAddressManualAllocateRequest,
)
from tests.deletion_guard_helpers import APP_DIR, REPO_ROOT, scan_deleted_at_writes

#: G-F021-1：F021 契约要求的两个端点（method, path）。
EXPECTED_ALLOCATION_ROUTES = {
    ("POST", "/ip-addresses/allocate"),
    ("POST", "/ip-addresses/allocate-manual"),
}

#: G-F021-5：SQLSTATE 单一映射的键集合（F021 不得新增）。
EXPECTED_SQLSTATE_KEYS = {"23502", "23514", "23505", "23503", "23P01"}

#: G-F021-8：IPv4 纯函数必须唯一实现于 ``app/ip_address_ranges/ipv4.py``。
IPV4_PURE_FUNCTIONS = ("parse_ipv4", "format_ipv4", "extract_ipv4_for_guard")
IPV4_OWNER = "backend/app/ip_address_ranges/ipv4.py"


def _allocation_sources() -> list[tuple[str, str]]:
    return [
        (str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8"))
        for path in sorted((APP_DIR / "ip_allocations").rglob("*.py"))
    ]


def _openapi() -> dict:
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


# --------------------------------------------------------------------------- #
# G-F021-1：分配路由交付面恰 2 个端点，且挂在 /api/ip-addresses 下
# --------------------------------------------------------------------------- #
def test_g_f021_1_router_registers_exactly_two_endpoints():
    routes = {
        (method, route.path)
        for route in ip_allocations_router.routes
        for method in route.methods
    }
    assert routes == EXPECTED_ALLOCATION_ROUTES


def test_g_f021_1_global_surface_has_allocation_paths():
    paths = _openapi()["paths"]
    assert set(paths) >= {
        "/api/ip-addresses/allocate",
        "/api/ip-addresses/allocate-manual",
    }
    for path in ("/api/ip-addresses/allocate", "/api/ip-addresses/allocate-manual"):
        assert set(paths[path]) == {"post"}


# --------------------------------------------------------------------------- #
# G-F021-2：请求 schema 封闭；响应复用 F005 的 IpAddressRead，无 cluster_id
# --------------------------------------------------------------------------- #
def test_g_f021_2_request_schemas_are_closed():
    # F023 演进：自动分配请求字段集合精确演进为
    # ``{network_interface_id, ip_address_range_id}``（两字段均必填）。
    assert set(IpAddressAutoAllocateRequest.model_fields) == {
        "network_interface_id",
        "ip_address_range_id",
    }
    assert set(IpAddressManualAllocateRequest.model_fields) == {
        "network_interface_id",
        "ip_address",
    }
    assert IpAddressAutoAllocateRequest.model_config.get("extra") == "forbid"
    assert IpAddressManualAllocateRequest.model_config.get("extra") == "forbid"


def test_g_f021_2_response_reuses_ip_address_read_without_cluster_id():
    components = _openapi()["components"]["schemas"]
    for name in ("IpAddressAutoAllocateRequest", "IpAddressManualAllocateRequest"):
        properties = components[name]["properties"]
        assert "cluster_id" not in properties
        assert not ({"status", "deleted_at", "mode", "reserved_addresses"} & set(properties))

    for path in ("/api/ip-addresses/allocate", "/api/ip-addresses/allocate-manual"):
        response = _openapi()["paths"][path]["post"]["responses"]["201"]
        schema = response["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/IpAddressRead")
    assert set(components["IpAddressRead"]["properties"]) == {
        "id",
        "network_interface_id",
        "ip_address",
        "created_at",
        "updated_at",
    }


# --------------------------------------------------------------------------- #
# G-F021-3：分配模块零 deleted_at 写入（唯一软删写入路径仍为 deletion/service.py）
# --------------------------------------------------------------------------- #
def test_g_f021_3_allocation_module_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "ip_allocations") == {}


# --------------------------------------------------------------------------- #
# G-F021-4：分配模块零 cluster_id 写入 / 零直接构造 IpAddress
#   写入必须经 app/ip_addresses/service.py::create_ip_address（R-01）
# --------------------------------------------------------------------------- #
def test_g_f021_4_allocation_module_never_constructs_ip_address_or_writes_cluster_id():
    offenders: list[str] = []
    for relpath, source in _allocation_sources():
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                # 不得构造 IpAddress(...)（含 cluster_id=）——所有写入经 create_ip_address。
                if callee == "IpAddress":
                    offenders.append(f"{relpath}: IpAddress(...)")
                if callee == "setattr" and len(node.args) >= 2:
                    second = node.args[1]
                    if isinstance(second, ast.Constant) and second.value == "cluster_id":
                        offenders.append(f"{relpath}: setattr(..., 'cluster_id', ...)")
                if callee in {"values", "dict"} and any(
                    kw.arg == "cluster_id" for kw in node.keywords
                ):
                    offenders.append(f"{relpath}: {callee}(cluster_id=...)")
                for arg in node.args:
                    if isinstance(arg, ast.Dict) and any(
                        isinstance(key, ast.Constant) and key.value == "cluster_id"
                        for key in arg.keys
                    ):
                        offenders.append(f"{relpath}: dict literal with cluster_id")
                if callee in {"text", "execute", "exec_driver_sql"}:
                    for arg in node.args:
                        if (
                            isinstance(arg, ast.Constant)
                            and isinstance(arg.value, str)
                            and "cluster_id" in arg.value
                        ):
                            offenders.append(f"{relpath}: raw SQL with cluster_id")
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "cluster_id":
                        offenders.append(f"{relpath}: x.cluster_id = ...")
    assert offenders == [], f"分配模块不得写 cluster_id / 直接构造 IpAddress：{offenders}"


def test_g_f021_4_allocation_writes_go_through_create_ip_address():
    sources = dict(_allocation_sources())
    service = sources["backend/app/ip_allocations/service.py"]
    assert "from app.ip_addresses.service import create_ip_address" in service
    assert "create_ip_address(" in service


# --------------------------------------------------------------------------- #
# G-F021-5：SQLSTATE 单一映射键集合不变（不新增映射）
# --------------------------------------------------------------------------- #
def test_g_f021_5_sqlstate_map_keys_unchanged():
    assert set(SQLSTATE_MAP) == EXPECTED_SQLSTATE_KEYS


# --------------------------------------------------------------------------- #
# G-F021-6：无新增分配 migration；head 已由 F022 推进到 0010（不得弱化）
# --------------------------------------------------------------------------- #
def test_g_f021_6_migration_head_still_0009():
    from tests.database.helpers import MIGRATION_HEAD

    assert MIGRATION_HEAD == "0010_f022_ip_range_metadata"


# --------------------------------------------------------------------------- #
# G-F021-7：不引入分配 / 预留表（复用 ip_addresses / ip_address_ranges）
# --------------------------------------------------------------------------- #
def test_g_f021_7_no_allocation_tables_registered():
    import app.models  # noqa: F401  (注册全部模型)
    from app.db.base import Base

    for name in Base.metadata.tables:
        lowered = name.lower()
        assert "allocation" not in lowered, name
        assert "reservation" not in lowered, name
        assert "assigned" not in lowered, name


# --------------------------------------------------------------------------- #
# G-F021-8：唯一一份 IPv4 解析器；分配模块复用 ip_address_ranges.ipv4
# --------------------------------------------------------------------------- #
def test_g_f021_8_ipv4_helpers_have_a_single_definition():
    definitions: list[tuple[str, str]] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        relpath = str(path.relative_to(REPO_ROOT))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name in IPV4_PURE_FUNCTIONS:
                definitions.append((relpath, node.name))
    assert {relpath for relpath, _ in definitions} == {IPV4_OWNER}, definitions
    assert {name for _, name in definitions} == set(IPV4_PURE_FUNCTIONS)


def test_g_f021_8_allocation_module_reuses_ipv4_helpers():
    sources = dict(_allocation_sources())
    service = sources["backend/app/ip_allocations/service.py"]
    assert "from app.ip_address_ranges.ipv4 import" in service
    assert "parse_ipv4" in service
    assert "format_ipv4" in service
    # 不得自带第二份解析实现。
    for name, _ in sources.items():
        assert "def parse_ipv4" not in sources[name]
        assert "def format_ipv4" not in sources[name]