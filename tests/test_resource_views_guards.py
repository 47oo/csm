"""F010 结构 / 静态 guard（G-010-1 ~ G-010-8）。

把「交付面恰为一条只读聚合端点」「404 单一网关」「五类成员委托既有 canonical
过滤」「无第二条软删过滤路径」「不越界到 Cluster / 状态 / 通用关系引擎」变成
会失败的测试，而非口头约定
（``docs/architecture/f010-resource-detail-handoff.md`` Test Work）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.resource_views.router import router as resource_views_router
from tests.conftest import OFFLINE_DSN
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
)

RELATED_PATH = "/api/bare-metals/{bare_metal_id}/related"
RELATED_MODULE_PATH = "/bare-metals/{bare_metal_id}/related"
RESOURCE_VIEWS_DIR = APP_DIR / "resource_views"

#: 顶层五类字段 == 元素类型复用的 canonical ``*Read``。
TOP_LEVEL_FIELDS = {
    "network_interfaces": "NetworkInterfaceRead",
    "ip_addresses": "IpAddressRead",
    "virtual_machines": "VirtualMachineRead",
    "containers": "ContainerRead",
    "services": "ServiceRead",
}

#: G-010-1：F010 之前既有的只读 GET 路由（必须全部保留）。
ROUTES_BEFORE_F010 = {
    "/api/health",
    "/api/clusters",
    "/api/clusters/by-name/{cluster_name}",
    "/api/clusters/{cluster_id}",
    "/api/clusters/by-name/{cluster_name}/bare-metals",
    "/api/bare-metals",
    "/api/bare-metals/{bare_metal_id}",
    "/api/virtual-machines",
    "/api/virtual-machines/{virtual_machine_id}",
    "/api/network-interfaces",
    "/api/network-interfaces/{network_interface_id}",
    "/api/ip-addresses",
    "/api/ip-addresses/{ip_address_id}",
    "/api/containers",
    "/api/containers/{container_id}",
    "/api/services",
    "/api/services/{service_id}",
    "/api/auth/session",
}

#: G-010-6：新模块源码不得出现的越界 / 通用关系引擎 token。
FORBIDDEN_SOURCE_TOKENS = (
    # F010 REV-2 加固：``deleted_at`` 必须在**源码级**被禁，而不能只靠
    # ``scan_deleted_at_writes``（后者只看**写入**形态）。架构 REQUIRED #2 要求
    # resource_views 不得出现**任何** ``deleted_at`` 表达式（含只读活跃过滤谓词，
    # 例如 ``.deleted_at.is_(None)``）——那会构成第二条活跃过滤路径（ADR-0004）。
    "deleted_at",
    "cluster_id",
    "cluster_name",
    "status",
    "state",
    "graph",
    "recursive",
    "recurse",
    "traverse",
    "topology",
    "adjacency",
    "networkx",
)

#: G-010-8：F009 交付的 Cluster 视角路径集合（F010 不得新增）。
F009_CLUSTER_PATHS = {
    "/api/clusters",
    "/api/clusters/by-name/{cluster_name}",
    "/api/clusters/{cluster_id}",
    "/api/clusters/by-name/{cluster_name}/bare-metals",
}


def _openapi() -> dict:
    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


def _component_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _operation() -> dict:
    return _openapi()["paths"][RELATED_PATH]["get"]


# --------------------------------------------------------------------------- #
# G-010-1：EXPECTED_GET_ROUTES 追加而非替换；既有成员全部保留
# --------------------------------------------------------------------------- #
def test_g010_1_expected_get_routes_appended_not_replaced():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES

    assert RELATED_PATH in EXPECTED_GET_ROUTES, "必须追加聚合端点路径"
    missing = ROUTES_BEFORE_F010 - EXPECTED_GET_ROUTES
    assert missing == set(), f"既有只读 GET 路由被删除：{missing}"


# --------------------------------------------------------------------------- #
# G-010-2：交付面封闭（恰一条 GET）
# --------------------------------------------------------------------------- #
def test_g010_2_resource_views_router_registers_exactly_one_get():
    routes = {
        (method, route.path) for route in resource_views_router.routes for method in route.methods
    }
    assert routes == {("GET", RELATED_MODULE_PATH)}


# --------------------------------------------------------------------------- #
# G-010-3：响应 schema 键恰五类；每类 items schema 复用对应 canonical *Read
# --------------------------------------------------------------------------- #
def test_g010_3_response_schema_is_closed_and_reuses_canonical_reads():
    components = _openapi()["components"]["schemas"]
    response_ref = _openapi()["paths"][RELATED_PATH]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert _component_name(response_ref) == "RelatedResourcesRead"
    schema = components[_component_name(response_ref)]
    assert set(schema["properties"]) == set(TOP_LEVEL_FIELDS)
    assert set(schema["required"]) == set(TOP_LEVEL_FIELDS)

    for field, read_name in TOP_LEVEL_FIELDS.items():
        set_schema = components[_component_name(schema["properties"][field]["$ref"])]
        assert set(set_schema["properties"]) == {"items", "total"}
        item_ref = set_schema["properties"]["items"]["items"]["$ref"]
        assert _component_name(item_ref) == read_name, f"{field} 元素 schema 必须复用 {read_name}"
        assert read_name in components


def test_g010_3_no_forbidden_keys_in_response_schema():
    components = _openapi()["components"]["schemas"]
    forbidden = ("deleted_at", "cluster_id", "cluster_name", "status", "state")
    for name, read_name in TOP_LEVEL_FIELDS.items():
        keys = set(components[read_name]["properties"])
        found = {token for token in forbidden for key in keys if token in key}
        assert found == set(), f"{name}/{read_name} 不得含越界字段：{found}"


# --------------------------------------------------------------------------- #
# G-010-4：请求封闭（无请求体；参数恰 {bare_metal_id}；无 Cluster / 软删 / 载体参数）
# --------------------------------------------------------------------------- #
def test_g010_4_request_surface_is_closed():
    operation = _operation()
    assert "requestBody" not in operation

    names = {param.get("name") for param in operation.get("parameters", [])}
    assert names == {"bare_metal_id"}
    for token in ("cluster", "include_deleted", "carrier", "deleted"):
        assert not any(token in (name or "").lower() for name in names)


# --------------------------------------------------------------------------- #
# G-010-5：软删单一性
# --------------------------------------------------------------------------- #
def test_g010_5_resource_views_writes_no_deleted_at():
    assert scan_deleted_at_writes(RESOURCE_VIEWS_DIR) == {}


def test_g010_5_source_token_guard_covers_read_predicates_too():
    """F010 REV-2 回归：源码 token guard 必须同时盖住**只读**的 deleted_at 谓词。

    ``scan_deleted_at_writes`` 只识别写入形态；评审注入只读谓词 ``.deleted_at.is_(None)``
    时该 guard 不失败。故 ``deleted_at`` 必须同时列入 ``FORBIDDEN_SOURCE_TOKENS``
    （扫源码文本，写入与读取均命中）。本测试固定该事实，防止它被后人移除。
    """
    assert "deleted_at" in FORBIDDEN_SOURCE_TOKENS
    probe = "row = session.scalars(select(X).where(X.deleted_at.is_(None))).all()"
    assert any(token in probe.lower() for token in FORBIDDEN_SOURCE_TOKENS)


def test_g010_5_global_deleted_at_write_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


# --------------------------------------------------------------------------- #
# G-010-6：源码无越界 token；无自递归函数
# --------------------------------------------------------------------------- #
def test_g010_6_source_has_no_forbidden_tokens():
    offenders: list[str] = []
    for path in sorted(RESOURCE_VIEWS_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_SOURCE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert offenders == [], f"resource_views 模块不得出现越界 token：{offenders}"


def test_g010_6_no_self_recursive_function():
    offenders: list[str] = []
    for path in sorted(RESOURCE_VIEWS_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == node.name
                ):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {node.name}")
    assert offenders == [], f"不得存在自递归函数：{offenders}"


# --------------------------------------------------------------------------- #
# G-010-7：二级路径恰为 {.../related}
# --------------------------------------------------------------------------- #
def test_g010_7_nested_paths_under_bare_metal_id_are_only_related():
    prefix = "/api/bare-metals/{bare_metal_id}/"
    paths = {path for path in _openapi()["paths"] if path.startswith(prefix)}
    assert paths == {RELATED_PATH}


# --------------------------------------------------------------------------- #
# G-010-8：未新增 Cluster 视角
# --------------------------------------------------------------------------- #
def test_g010_8_no_new_cluster_view_paths():
    paths = {path for path in _openapi()["paths"] if path.startswith("/api/clusters")}
    assert paths == F009_CLUSTER_PATHS


def test_g010_source_files_exist_under_owned_paths():
    assert (REPO_ROOT / "backend/app/resource_views/router.py").exists()
    assert (REPO_ROOT / "backend/app/resource_views/service.py").exists()
    assert (REPO_ROOT / "backend/app/resource_views/schemas.py").exists()
    assert Path(RESOURCE_VIEWS_DIR).is_dir()
