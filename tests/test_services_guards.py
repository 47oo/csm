"""F008 Service 静态 / 结构 guard。

把「字段封闭」「载体表示恰为 carrier_type + carrier_id」「无状态 / 无集群维度」
「无凭据 / 健康 / 监控 / 位置字段」「未定义约束不实现」「绑定写入路径恰为一次 INSERT」
「活跃子检查点显式声明且被消费」「唯一软删写入路径」「无解绑路径」「路由交付面封闭」
「保留 allow-list 防线」变成会失败的测试（``docs/architecture/f008-service-handoff.md``
§9 / §10）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.bare_metals.deletion import BARE_METAL_ACTIVE_CHILD_CHECKS
from app.clusters.deletion import CLUSTER_ACTIVE_CHILD_CHECKS
from app.containers.deletion import CONTAINER_ACTIVE_CHILD_CHECKS
from app.services.deletion import (
    SERVICE_ACTIVE_CHILD_CHECKS,
    has_active_services_on_bare_metal,
    has_active_services_on_container,
    has_active_services_on_virtual_machine,
)
from app.services.router import router as services_router
from app.services.schemas import OPTIONAL_FIELDS
from app.virtual_machines.deletion import VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS
from tests.deletion_guard_helpers import (
    ALLOWED_DELETED_AT_WRITER,
    APP_DIR,
    REPO_ROOT,
    scan_deleted_at_writes,
    scan_undelete_writes,
)

FORBIDDEN_CONSTRAINT_ATTRS = (
    "min_length",
    "max_length",
    "pattern",
    "strip_whitespace",
    "to_lower",
    "to_upper",
)

SERVICE_READ_FIELDS = {
    "id",
    "name",
    "service_type",
    "url",
    "port",
    "protocol",
    "owner",
    "description",
    "carriers",
    "created_at",
    "updated_at",
}

SERVICE_TABLE_COLUMNS = {
    "id",
    "name",
    *OPTIONAL_FIELDS,
    "created_at",
    "updated_at",
    "deleted_at",
}

SERVICE_CARRIER_TABLE_COLUMNS = {
    "id",
    "service_id",
    "bare_metal_id",
    "virtual_machine_id",
    "container_id",
}

FORBIDDEN_MODULE_TOKENS = (
    "credential",
    "secret",
    "password",
    "token",
    "health",
    "monitor",
    "alert",
    "discover",
    "sync",
    "external_id",
    "data_center",
    "datacenter",
    "location",
    "room",
    "rack",
    "u_position",
    "site",
    "campus",
)

FORBIDDEN_CLUSTER_TOKENS = ("cluster_id", "cluster_name")


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


def _module_sources() -> list[Path]:
    return sorted((APP_DIR / "services").rglob("*.py"))


def _openapi() -> dict:
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


# --------------------------------------------------------------------------- #
# G-1：字段封闭（契约 §2；恰 11 字段；含 carriers）
# --------------------------------------------------------------------------- #
def test_g1_service_read_schema_is_closed():
    from app.services.schemas import ServiceRead

    assert set(ServiceRead.model_fields) == SERVICE_READ_FIELDS
    assert "deleted_at" not in ServiceRead.model_fields
    assert "status" not in ServiceRead.model_fields
    for token in FORBIDDEN_CLUSTER_TOKENS:
        assert token not in ServiceRead.model_fields


def test_g1_create_and_update_schemas_are_closed():
    from app.services.schemas import ServiceCreate, ServiceUpdate

    assert ServiceCreate.model_config.get("extra") == "forbid"
    assert ServiceUpdate.model_config.get("extra") == "forbid"

    assert set(ServiceCreate.model_fields) == {"name", "carriers", *OPTIONAL_FIELDS}
    assert set(ServiceUpdate.model_fields) == set(OPTIONAL_FIELDS)
    assert set(ServiceUpdate.model_fields) != set(ServiceCreate.model_fields)
    assert "carriers" not in ServiceUpdate.model_fields, "PATCH 不得接受载体绑定（AC-48）"
    assert "name" not in ServiceUpdate.model_fields
    for forbidden in ("id", "carrier_type", "carrier_id", "deleted_at", "status", "cluster_id"):
        assert forbidden not in ServiceUpdate.model_fields, forbidden


def test_g1_carrier_ref_schema_is_closed():
    from app.services.schemas import CarrierRef

    assert set(CarrierRef.model_fields) == {"carrier_type", "carrier_id"}
    assert CarrierRef.model_config.get("extra") == "forbid"
    assert "bare_metal_id" not in CarrierRef.model_fields
    assert "virtual_machine_id" not in CarrierRef.model_fields
    assert "container_id" not in CarrierRef.model_fields


# --------------------------------------------------------------------------- #
# G-2：ORM 列 / 索引 / FK / CHECK
# --------------------------------------------------------------------------- #
def test_g2_services_model_columns_exact():
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["services"].columns}
    assert columns == SERVICE_TABLE_COLUMNS
    assert "status" not in columns and "state" not in columns
    assert not any("cluster" in column for column in columns)
    assert not any(column in columns for column in SERVICE_CARRIER_TABLE_COLUMNS - {"id"})


def test_g2_service_carriers_model_columns_exact():
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["service_carriers"].columns}
    assert columns == SERVICE_CARRIER_TABLE_COLUMNS
    assert "deleted_at" not in columns
    assert "created_at" not in columns and "updated_at" not in columns
    assert "carrier_type" not in columns


def test_g2_services_indexes_and_no_check():
    from app.db.base import Base

    table = Base.metadata.tables["services"]
    index_names = {index.name for index in table.indexes}
    assert index_names == {"ux_services_name_active"}
    index = next(index for index in table.indexes if index.name == "ux_services_name_active")
    assert index.unique is True

    check_names = {c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
    assert check_names == set()


def test_g2_service_carriers_indexes_fk_and_check():
    from app.db.base import Base

    table = Base.metadata.tables["service_carriers"]
    index_names = {index.name for index in table.indexes}
    assert index_names == {
        "ux_service_carriers_service_bare_metal",
        "ux_service_carriers_service_virtual_machine",
        "ux_service_carriers_service_container",
        "ix_service_carriers_bare_metal_id",
        "ix_service_carriers_virtual_machine_id",
        "ix_service_carriers_container_id",
        "ix_service_carriers_service_id",
    }

    fks = {fk.name: fk for fk in table.foreign_keys}
    assert set(fks) == {
        "fk_service_carriers_service",
        "fk_service_carriers_bare_metal",
        "fk_service_carriers_virtual_machine",
        "fk_service_carriers_container",
    }
    for fk in fks.values():
        assert fk.ondelete == "RESTRICT"
        assert fk.onupdate == "RESTRICT"

    checks = {
        c.name: str(c.sqltext)
        for c in table.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert set(checks) == {"ck_service_carriers_exactly_one_carrier"}
    assert "num_nonnulls" in checks["ck_service_carriers_exactly_one_carrier"]


def test_g2_models_have_no_relationships():
    from app.models.service import Service
    from app.models.service_carrier import ServiceCarrier

    assert list(Service.__mapper__.relationships) == []
    assert list(ServiceCarrier.__mapper__.relationships) == []


# --------------------------------------------------------------------------- #
# G-3：OpenAPI 服务端点无状态 / 无集群维度参数
# --------------------------------------------------------------------------- #
def test_g3_openapi_service_endpoints_have_closed_params():
    paths = _openapi()["paths"]
    for path, operations in paths.items():
        if not path.startswith("/api/services"):
            continue
        assert "status" not in path.lower()
        for operation in operations.values():
            names = {p.get("name") for p in operation.get("parameters", [])}
            for name in names:
                assert "status" not in (name or "").lower()
                for token in FORBIDDEN_CLUSTER_TOKENS:
                    assert token not in (name or "").lower()
                assert "deleted" not in (name or "").lower()
                assert "include" not in (name or "").lower()


# --------------------------------------------------------------------------- #
# G-4：越界 token（服务端点 + app/services 源码）
# --------------------------------------------------------------------------- #
def test_g4_no_forbidden_tokens_in_service_openapi_paths():
    offenders = [
        path
        for path in _openapi()["paths"]
        if path.startswith("/api/services")
        and any(token in path.lower() for token in FORBIDDEN_MODULE_TOKENS)
    ]
    assert offenders == [], f"服务端点不得出现越界 token：{offenders}"


def test_g4_no_forbidden_tokens_in_service_module_source():
    offenders: list[str] = []
    for path in _module_sources():
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_MODULE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert offenders == [], f"services 模块不得出现越界字段 token：{offenders}"


def test_g4_no_cluster_tokens_in_service_module_source():
    offenders: list[str] = []
    for path in _module_sources():
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_CLUSTER_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert offenders == [], f"services 模块不得出现集群维度 token：{offenders}"


# --------------------------------------------------------------------------- #
# G-5：未定义约束「不实现」
# --------------------------------------------------------------------------- #
def test_g5_service_schemas_have_no_undefined_constraints():
    from app.services.schemas import CarrierRef, ServiceCreate, ServiceUpdate

    for model in (ServiceCreate, ServiceUpdate):
        for field in OPTIONAL_FIELDS:
            assert _field_constraint_flags(model, field) == set(), f"{model.__name__}.{field}"
        decorators = model.__pydantic_decorators__
        assert decorators.validators == {}
        assert decorators.field_validators == {}
    for field in ("name",):
        assert _field_constraint_flags(ServiceCreate, field) == set(), field
    assert _field_constraint_flags(CarrierRef, "carrier_id") == set()
    # ``carriers`` 的 ``min_length=1`` 是**已确认**的 R-SVC-005「至少 1 个载体」要求，
    # 不是未定义约束；断言其为恰 1，而非无约束。
    constraints = [
        meta
        for meta in ServiceCreate.model_fields["carriers"].metadata
        if hasattr(meta, "min_length")
    ]
    assert [meta.min_length for meta in constraints] == [1]
    for meta in constraints:
        assert getattr(meta, "max_length", None) in (None, False)


# --------------------------------------------------------------------------- #
# G-6：EXPECTED_GET_ROUTES 追加两条
# --------------------------------------------------------------------------- #
def test_g6_expected_get_routes_contains_service_routes():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES

    assert "/api/services" in EXPECTED_GET_ROUTES
    assert "/api/services/{service_id}" in EXPECTED_GET_ROUTES


# --------------------------------------------------------------------------- #
# G-7：BOUNDARY_TOKENS 演进 + allow-list 防线保留
# --------------------------------------------------------------------------- #
def test_g7_boundary_tokens_removed_service_but_allowlist_retained():
    from tests import test_cluster_views_guards as cv
    from tests.test_structure_guard import APPROVED_API_PREFIXES

    assert "service" not in cv.BOUNDARY_TOKENS
    assert "services" in APPROVED_API_PREFIXES

    # 全局扫描保持：test_g009_2 仍对全部 OpenAPI path 扫描（不得删除 / 不得收窄）。
    source = (REPO_ROOT / "tests/test_cluster_views_guards.py").read_text(encoding="utf-8")
    assert "test_g009_2_no_forbidden_resource_tokens_in_any_path" in source
    assert 'for path in _openapi()["paths"]' in source

    # allow-list 测试必须保留（F008 后真正的越界端点防线）。
    structure = (REPO_ROOT / "tests/test_structure_guard.py").read_text(encoding="utf-8")
    assert "test_product_api_surface_is_closed" in structure


# --------------------------------------------------------------------------- #
# G-8：唯一软删写入路径 allow-list 不变；services 模块不写 deleted_at
# --------------------------------------------------------------------------- #
def test_g8_deleted_at_writer_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


def test_g8_service_module_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "services") == {}
    assert scan_undelete_writes(APP_DIR / "services") == []


# --------------------------------------------------------------------------- #
# G-9：绑定写入路径恰为一次 INSERT（无 UPDATE / DELETE / session.delete）
# --------------------------------------------------------------------------- #
def test_g9_binding_writes_are_insert_only():
    offenders: list[str] = []
    for path in _module_sources():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        for needle in (
            "session.delete(",
            "delete(ServiceCarrier",
            "update(ServiceCarrier",
            "DELETE FROM service_carriers",
            "UPDATE service_carriers",
        ):
            if needle in text:
                offenders.append(f"{rel}: {needle}")
    assert offenders == [], f"绑定写入路径只允许 INSERT：{offenders}"

    # 源码确实存在 INSERT（ServiceCarrier 构造 + add_all）。
    repository = (APP_DIR / "services" / "repository.py").read_text(encoding="utf-8")
    assert "ServiceCarrier(" in repository
    assert "add_all" in repository


def test_g9_no_unbind_endpoints_or_params():
    paths = _openapi()["paths"]
    service_paths = {path for path in paths if path.startswith("/api/services")}
    assert service_paths == {"/api/services", "/api/services/{service_id}"}
    for path in service_paths:
        assert "carrier" not in path.lower()
        for operation in paths[path].values():
            param_names = {p.get("name") for p in operation.get("parameters", [])}
            assert param_names == {"page", "page_size", "carrier_type", "carrier_id"} or (
                param_names == {"service_id"} or param_names == set()
            ), (path, param_names)
    # 无 PUT（无整体替换语义）。
    methods = {method.lower() for path in service_paths for method in paths[path]}
    assert "put" not in methods


# --------------------------------------------------------------------------- #
# G-10：活跃子检查点接线（三载体追加、CLUSTER 不变）
# --------------------------------------------------------------------------- #
def test_g10_service_active_child_checks_explicitly_empty_and_consumed():
    assert isinstance(SERVICE_ACTIVE_CHILD_CHECKS, tuple)
    assert SERVICE_ACTIVE_CHILD_CHECKS == ()
    source = (APP_DIR / "services" / "service.py").read_text(encoding="utf-8")
    assert "SERVICE_ACTIVE_CHILD_CHECKS" in _soft_delete_active_children_args(source)


def test_g10_carrier_checks_contain_service_checks():
    assert has_active_services_on_bare_metal in BARE_METAL_ACTIVE_CHILD_CHECKS
    assert has_active_services_on_virtual_machine in VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS
    assert has_active_services_on_container in CONTAINER_ACTIVE_CHILD_CHECKS
    assert CONTAINER_ACTIVE_CHILD_CHECKS, "F008 后 Container 检查不得为空"


def test_g10_cluster_checks_unchanged():
    from app.bare_metals.deletion import has_active_bare_metals

    assert CLUSTER_ACTIVE_CHILD_CHECKS == (has_active_bare_metals,)
    assert has_active_services_on_bare_metal not in CLUSTER_ACTIVE_CHILD_CHECKS


# --------------------------------------------------------------------------- #
# G-11：路由交付面封闭（恰 5 个端点）
# --------------------------------------------------------------------------- #
def test_g11_service_router_registers_exactly_five_endpoints():
    routes = {(method, route.path) for route in services_router.routes for method in route.methods}
    assert routes == {
        ("POST", "/services"),
        ("GET", "/services"),
        ("GET", "/services/{service_id}"),
        ("PATCH", "/services/{service_id}"),
        ("DELETE", "/services/{service_id}"),
    }


# --------------------------------------------------------------------------- #
# G-12：migration head / down_revision
# --------------------------------------------------------------------------- #
def test_g12_migration_head():
    from tests.database.helpers import MIGRATION_HEAD

    assert MIGRATION_HEAD == "0008_f008_services"
    migration = REPO_ROOT / "backend/migrations/versions/0008_f008_services.py"
    source = migration.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0007_f007_containers"' in source


# --------------------------------------------------------------------------- #
# G-13：无 CASCADE / 无 lower / 无 COLLATE
# --------------------------------------------------------------------------- #
def test_g13_no_cascade_in_orm():
    from app.db.base import Base

    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.ondelete != "CASCADE", f"{table.name}.{fk.name}"


def test_g13_no_lower_or_collate_in_service_module():
    sources = [path.read_text(encoding="utf-8") for path in _module_sources()]
    sources.append((APP_DIR / "models" / "service.py").read_text(encoding="utf-8"))
    sources.append((APP_DIR / "models" / "service_carrier.py").read_text(encoding="utf-8"))
    sources.append(
        (REPO_ROOT / "backend/migrations/versions/0008_f008_services.py").read_text(
            encoding="utf-8"
        )
    )
    for source in sources:
        lowered = source.lower()
        assert "collate=" not in lowered
        assert "func.lower" not in lowered
