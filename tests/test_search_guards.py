"""F019 搜索结果聚合视图结构 / 静态 guard（继承 G-018-1 ~ G-018-8，新增 G-019-3）。

把「交付面恰为一条只读搜索端点」「范围推导复用 F010 唯一入口」「无第二条软删
过滤路径」「大小写折叠仅限 search 模块」「资源表示复用 canonical *Read」
「聚合响应封闭（role / group_key / derivation_path）」「既有 guard 只增不减」
变成会失败的测试，而非口头约定
（``docs/architecture/f019-search-result-aggregation-handoff.md`` Test Work）。

**只增不减**：``EXPECTED_GET_ROUTES`` 与 F010 ``F009_CLUSTER_PATHS`` 追加而不替换；
越界 token（相似度 / 跨集群 / 软删 / 统计）禁止不被新增排序放开。
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.search.router import router as search_router
from tests.conftest import OFFLINE_DSN
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
)

SEARCH_PATH = "/api/clusters/{cluster_id}/search"
SEARCH_MODULE_PATH = "/clusters/{cluster_id}/search"
SEARCH_DIR = APP_DIR / "search"

#: G-018-6：``resource`` 的 anyOf 恰为六个 canonical ``*Read``。
CANONICAL_READS = {
    "BareMetalRead",
    "NetworkInterfaceRead",
    "IpAddressRead",
    "VirtualMachineRead",
    "ContainerRead",
    "ServiceRead",
}

#: G-018-6：``resource_type`` 枚举恰六值。
RESOURCE_TYPE_VALUES = {
    "BARE_METAL",
    "NETWORK_INTERFACE",
    "IP_ADDRESS",
    "VIRTUAL_MACHINE",
    "CONTAINER",
    "SERVICE",
}

#: G-018-7：search 模块源码不得出现的越界 / 通用搜索 token。
FORBIDDEN_SOURCE_TOKENS = (
    "export",
    "csv",
    "excel",
    "order_by",
    "orderby",
    "sort_by",
    "status_filter",
    "relevance",
    "rank_by",
    "tsvector",
    "tsquery",
    "trigram",
    "pg_trgm",
    "cross_cluster",
    "include_deleted",
    "undelete",
    "restore",
    "status",
    "state",
)

#: G-018-5：大小写折叠调用名（仅允许出现在 search 模块）。
CASE_FOLD_CALLS = {"lower", "casefold", "ilike"}

#: G-018-8：F009 四条 Cluster 视角路径（F018 追加时**必须保留**）。
F009_FOUR_PATHS = {
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


def _case_fold_call_lines(path: Path) -> list[int]:
    """返回源码中 ``X.lower/casefold/ilike(...)`` 调用的行号（AST，忽略 docstring）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in CASE_FOLD_CALLS
        ):
            lines.append(node.lineno)
    return lines


def _search_sources() -> list[Path]:
    return sorted(SEARCH_DIR.rglob("*.py"))


# --------------------------------------------------------------------------- #
# G-018-1：EXPECTED_GET_ROUTES 追加而非替换；既有成员全部保留
# --------------------------------------------------------------------------- #
def test_g018_1_expected_get_routes_appended_not_replaced():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES
    from tests.test_resource_views_guards import ROUTES_BEFORE_F010

    assert SEARCH_PATH in EXPECTED_GET_ROUTES, "必须追加搜索端点路径"
    missing = ROUTES_BEFORE_F010 - EXPECTED_GET_ROUTES
    assert missing == set(), f"既有只读 GET 路由被删除：{missing}"


# --------------------------------------------------------------------------- #
# G-018-2：交付面封闭（search 路由恰一条 GET；位于 /api 前缀下）
# --------------------------------------------------------------------------- #
def test_g018_2_search_router_registers_exactly_one_get():
    routes = {(method, route.path) for route in search_router.routes for method in route.methods}
    assert routes == {("GET", SEARCH_MODULE_PATH)}


def test_g018_2_search_endpoint_lives_under_api_and_needs_no_new_prefix():
    from tests.test_structure_guard import APPROVED_API_PREFIXES

    paths = _openapi()["paths"]
    assert SEARCH_PATH in paths
    first = SEARCH_PATH[len("/api/") :].split("/", 1)[0]
    assert first in APPROVED_API_PREFIXES, "首段 clusters 已批准，不得新增白名单成员"


# --------------------------------------------------------------------------- #
# G-018-3：软删单一性
# --------------------------------------------------------------------------- #
def test_g018_3_search_writes_no_deleted_at():
    assert scan_deleted_at_writes(SEARCH_DIR) == {}


def test_g018_3_global_deleted_at_write_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


# --------------------------------------------------------------------------- #
# G-018-4：范围推导复用 F010 唯一入口；源码无 deleted_at
# --------------------------------------------------------------------------- #
def test_g018_4_service_imports_and_calls_get_related_resources():
    service_path = SEARCH_DIR / "service.py"
    tree = ast.parse(service_path.read_text(encoding="utf-8"))

    imports_entry = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.resource_views.service"
        and any(alias.name == "get_related_resources" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imports_entry, "search/service.py 必须导入 app.resource_views.service"

    calls_entry = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_related_resources"
        for node in ast.walk(tree)
    )
    assert calls_entry, "search/service.py 必须调用 get_related_resources（不得重写推导）"


def test_g018_4_no_deleted_at_expression_in_search_sources():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _search_sources()
        if "deleted_at" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"search 模块不得出现任何 deleted_at 表达式：{offenders}"


# --------------------------------------------------------------------------- #
# G-018-5：大小写隔离（折叠调用仅允许出现在 search 模块）
# --------------------------------------------------------------------------- #
def test_g018_5_case_folding_calls_only_in_search_module():
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if SEARCH_DIR in path.parents or path == SEARCH_DIR:
            continue
        for lineno in _case_fold_call_lines(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert offenders == [], f"大小写折叠调用越界（仅限 search 模块）：{offenders}"


def test_g018_5_search_module_actually_folds_case():
    """guard 不得恒真：search 模块必须真的使用大小写折叠（至少一处调用）。"""
    called = [lineno for path in _search_sources() for lineno in _case_fold_call_lines(path)]
    assert called, "search 模块必须实际执行大小写折叠子串匹配"


def test_g018_5_resource_and_auth_repositories_are_case_preserving():
    targets = [
        APP_DIR / name / "repository.py"
        for name in (
            "clusters",
            "bare_metals",
            "network_interfaces",
            "ip_addresses",
            "virtual_machines",
            "containers",
            "services",
        )
    ] + [APP_DIR / "auth" / "repository.py"]
    offenders = [
        str(path.relative_to(REPO_ROOT)) for path in targets if _case_fold_call_lines(path)
    ]
    assert offenders == [], f"repository 层不得使用 lower/casefold/ilike：{offenders}"


# --------------------------------------------------------------------------- #
# G-018-6：响应 schema 封闭且复用 canonical *Read
# --------------------------------------------------------------------------- #
def test_g018_6_response_reuses_six_canonical_reads_and_closed_enum():
    spec = _openapi()
    components = spec["components"]["schemas"]

    schema_ref = spec["paths"][SEARCH_PATH]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    page_schema = components[_component_name(schema_ref)]
    assert set(page_schema["properties"]) == {"items", "total", "page", "page_size"}
    item_ref = page_schema["properties"]["items"]["items"]["$ref"]
    item_schema = components[_component_name(item_ref)]
    assert set(item_schema["properties"]) == {
        "resource_type",
        "id",
        "role",
        "group_key",
        "matched_fields",
        "derivation_path",
        "resource",
    }

    resource = item_schema["properties"]["resource"]
    assert "anyOf" in resource, f"resource 必须是联合（anyOf）：{resource}"
    assert {_component_name(ref["$ref"]) for ref in resource["anyOf"]} == CANONICAL_READS

    resource_type = item_schema["properties"]["resource_type"]
    if "$ref" in resource_type:
        resource_type = components[_component_name(resource_type["$ref"])]
    assert set(resource_type["enum"]) == RESOURCE_TYPE_VALUES


def test_g019_3_role_and_group_key_are_closed():
    """G-019-3：``role`` 恰两值；``group_key`` / ``derivation_path`` 元素恰 ResourceRef。"""
    spec = _openapi()
    components = spec["components"]["schemas"]

    page_ref = spec["paths"][SEARCH_PATH]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    page_schema = components[_component_name(page_ref)]
    item_ref = page_schema["properties"]["items"]["items"]["$ref"]
    item_schema = components[_component_name(item_ref)]

    role = item_schema["properties"]["role"]
    if "$ref" in role:
        role = components[_component_name(role["$ref"])]
    assert set(role["enum"]) == {"HIT", "RELATED"}

    group_key = item_schema["properties"]["group_key"]
    assert _component_name(group_key["$ref"]) == "ResourceRef"
    assert set(components["ResourceRef"]["properties"]) == {"resource_type", "id"}

    path = item_schema["properties"]["derivation_path"]
    array_schema = next(option for option in path["anyOf"] if option.get("type") == "array")
    assert _component_name(array_schema["items"]["$ref"]) == "ResourceRef"
    assert any(option.get("type") == "null" for option in path["anyOf"]), "须为可空"


def test_g018_6_response_carries_no_deleted_at():
    components = _openapi()["components"]["schemas"]
    for name in ("SearchResultRow", "ResourceRef"):
        assert "deleted_at" not in components[name]["properties"], name
    for read_name in CANONICAL_READS:
        assert "deleted_at" not in components[read_name]["properties"], read_name


# --------------------------------------------------------------------------- #
# G-018-7：源码无越界 token
# --------------------------------------------------------------------------- #
def test_g018_7_search_source_has_no_out_of_scope_tokens():
    offenders: list[str] = []
    for path in _search_sources():
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_SOURCE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert offenders == [], f"search 模块不得出现越界 token：{offenders}"


def test_g018_7_request_surface_is_closed():
    operation = _openapi()["paths"][SEARCH_PATH]["get"]
    assert "requestBody" not in operation
    names = {param.get("name") for param in operation.get("parameters", [])}
    assert names == {"cluster_id", "keyword", "page", "page_size"}
    for token in ("sort", "order", "status", "include_deleted", "carrier"):
        assert not any(token in (name or "").lower() for name in names), token


def test_g018_7_no_keyword_param_added_to_existing_endpoints():
    paths = _openapi()["paths"]
    offenders = [
        path
        for path, operations in paths.items()
        if path != SEARCH_PATH
        for operation in operations.values()
        if any(param.get("name") == "keyword" for param in operation.get("parameters", []))
    ]
    assert offenders == [], f"不得给既有端点追加 keyword 参数：{offenders}"


# --------------------------------------------------------------------------- #
# G-018-8：F010 guard 追加 search 路径（保留 F009 四条）；既有 G-010 全绿
# --------------------------------------------------------------------------- #
def test_g018_8_f009_cluster_paths_appended_not_replaced():
    from tests.test_resource_views_guards import F009_CLUSTER_PATHS

    assert SEARCH_PATH in F009_CLUSTER_PATHS, "必须追加搜索路径"
    missing = F009_FOUR_PATHS - F009_CLUSTER_PATHS
    assert missing == set(), f"F009 四条 Cluster 路径被删除：{missing}"
    assert F009_CLUSTER_PATHS == F009_FOUR_PATHS | {SEARCH_PATH}


def test_g018_8_openapi_cluster_paths_match_evolution_set():
    from tests.test_resource_views_guards import F009_CLUSTER_PATHS

    paths = {path for path in _openapi()["paths"] if path.startswith("/api/clusters")}
    assert paths == F009_CLUSTER_PATHS


def test_g018_8_resource_views_owns_no_search_path():
    paths = {path for path in _openapi()["paths"] if path.startswith("/api/bare-metals")}
    assert paths == {
        "/api/bare-metals",
        "/api/bare-metals/{bare_metal_id}",
        "/api/bare-metals/{bare_metal_id}/related",
    }
