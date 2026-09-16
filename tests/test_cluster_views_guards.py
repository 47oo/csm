"""F009 结构 / 静态 guard（G-009-1 ~ G-009-6）。

把「交付面恰为一条只读别名」「与 canonical 响应 schema 逐字段一致」
「不越界到 NIC / IP / VM / Container / Service」「无第二条软删过滤路径」
「不再新增领域字段」变成会失败的测试，而非口头约定
（``docs/architecture/f009-cluster-resource-view-handoff.md`` Test Work）。
"""

from __future__ import annotations

from pathlib import Path

from app.bare_metals.schemas import BareMetalRead
from app.cluster_views.router import router as cluster_views_router
from app.config import Settings
from app.main import create_app
from tests.conftest import OFFLINE_DSN
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
)

ALIAS_PATH = "/api/clusters/by-name/{cluster_name}/bare-metals"
CANONICAL_PATH = "/api/bare-metals"
CLUSTER_VIEWS_MODULE_PATH = "/clusters/by-name/{cluster_name}/bare-metals"

#: F002 §2 的封闭字段集合（恰 13 字段）。
BARE_METAL_READ_FIELDS = {
    "id",
    "cluster_id",
    "hostname",
    "status",
    "vendor",
    "model",
    "serial_number",
    "cpu",
    "memory",
    "gpu",
    "storage",
    "created_at",
    "updated_at",
}

#: G-009-1：F009 之前既有的只读 GET 路由（必须全部保留）。
ORIGINAL_GET_ROUTES = {
    "/api/health",
    "/api/clusters",
    "/api/clusters/by-name/{cluster_name}",
    "/api/clusters/{cluster_id}",
    "/api/bare-metals",
    "/api/bare-metals/{bare_metal_id}",
    "/api/auth/session",
}

#: G-009-2：R-QUERY-003 资源类型 token（F010 归属，F009 不得出现）。
BOUNDARY_TOKENS = (
    "network-interface",
    "network_interface",
    "ip-address",
    "ip_address",
    "virtual-machine",
    "virtual_machine",
    "container",
    "service",
)

#: G-009-4：不得新增的 Cluster 状态 / 位置 / 自动发现字段 token。
FORBIDDEN_FIELD_TOKENS = (
    "data_center",
    "datacenter",
    "location",
    "room",
    "rack",
    "u_position",
    "site",
    "campus",
    "cluster_status",
    "cluster_state",
    "discovered",
    "last_seen",
    "external_status_source",
)


def _openapi() -> dict:
    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


# --------------------------------------------------------------------------- #
# G-009-1：EXPECTED_GET_ROUTES 追加而非替换；既有成员全部保留
# --------------------------------------------------------------------------- #
def test_g009_1_expected_get_routes_evolved_not_replaced():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES

    assert ALIAS_PATH in EXPECTED_GET_ROUTES, "必须追加 alias 路径"
    missing = ORIGINAL_GET_ROUTES - EXPECTED_GET_ROUTES
    assert missing == set(), f"既有只读 GET 路由被删除：{missing}"


# --------------------------------------------------------------------------- #
# G-009-2：边界 token guard（全部 OpenAPI path）
# --------------------------------------------------------------------------- #
def test_g009_2_no_forbidden_resource_tokens_in_any_path():
    offenders = [
        path
        for path in _openapi()["paths"]
        if any(token in path.lower() for token in BOUNDARY_TOKENS)
    ]
    assert offenders == [], f"F009 不得注册其它资源端点：{offenders}"


# --------------------------------------------------------------------------- #
# G-009-3：响应 schema 封闭（alias == canonical；BareMetalRead 恰 13 字段）
# --------------------------------------------------------------------------- #
def test_g009_3_alias_response_schema_equals_canonical():
    paths = _openapi()["paths"]
    alias_schema = paths[ALIAS_PATH]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    canonical_schema = paths[CANONICAL_PATH]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert alias_schema == canonical_schema


def test_g009_3_bare_metal_read_has_exactly_thirteen_fields():
    assert set(BareMetalRead.model_fields) == BARE_METAL_READ_FIELDS
    assert "deleted_at" not in BareMetalRead.model_fields


# --------------------------------------------------------------------------- #
# G-009-4：字段封闭（cluster_views 源码 + alias 请求 / 响应）
# --------------------------------------------------------------------------- #
def test_g009_4_cluster_views_source_has_no_forbidden_field_tokens():
    module_dir = APP_DIR / "cluster_views"
    offenders: list[str] = []
    for path in sorted(module_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_FIELD_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert offenders == [], f"cluster_views 模块不得出现越界字段 token：{offenders}"


def test_g009_4_alias_request_and_parameters_are_closed():
    op = _openapi()["paths"][ALIAS_PATH]["get"]

    # 只读端点：无请求体。
    assert "requestBody" not in op

    param_names = {p.get("name") for p in op.get("parameters", [])}
    assert param_names == {"cluster_name", "page", "page_size"}
    assert not any(
        token in (name or "").lower() for name in param_names for token in FORBIDDEN_FIELD_TOKENS
    )


# --------------------------------------------------------------------------- #
# G-009-5：软删单一性
# --------------------------------------------------------------------------- #
def test_g009_5_cluster_views_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "cluster_views") == {}


def test_g009_5_global_deleted_at_write_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


# --------------------------------------------------------------------------- #
# G-009-6：交付面封闭（alias 路由集合恰为一条 GET）
# --------------------------------------------------------------------------- #
def test_g009_6_cluster_views_router_registers_exactly_one_get():
    routes = {
        (method, route.path) for route in cluster_views_router.routes for method in route.methods
    }
    assert routes == {("GET", CLUSTER_VIEWS_MODULE_PATH)}


def test_g009_6_openapi_alias_path_set_is_exactly_one():
    alias_paths = {
        path
        for path in _openapi()["paths"]
        if path.startswith("/api/clusters/by-name/") and path.endswith("/bare-metals")
    }
    assert alias_paths == {ALIAS_PATH}


def test_g009_6_source_file_exists_under_owned_paths():
    assert (REPO_ROOT / "backend/app/cluster_views/router.py").exists()
    assert (REPO_ROOT / "backend/app/cluster_views/service.py").exists()
    assert Path(APP_DIR / "cluster_views").is_dir()
