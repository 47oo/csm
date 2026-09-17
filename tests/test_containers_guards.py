"""F007 Container 静态 / 结构 guard（G-1 ~ G-15、T-26/T-27 演进）。

把「字段封闭」「载体表示恰为 carrier_type + carrier_id」「无状态 / 无集群维度」
「无 K8s / Docker / 运行时 / 位置字段」「未定义约束不实现」「活跃子检查点显式声明且被
消费」「唯一软删写入路径」「无 EAV / JSONB / 多态」「路由交付面封闭」变成会失败的测试，
而非口头约定（``docs/architecture/f007-container-handoff.md`` §7 / §10）。
"""

from __future__ import annotations

import ast

from app.bare_metals.deletion import BARE_METAL_ACTIVE_CHILD_CHECKS
from app.clusters.deletion import CLUSTER_ACTIVE_CHILD_CHECKS
from app.containers.deletion import (
    CONTAINER_ACTIVE_CHILD_CHECKS,
    has_active_containers_on_bare_metal,
    has_active_containers_on_virtual_machine,
)
from app.containers.router import router as containers_router
from app.containers.schemas import OPTIONAL_FIELDS
from app.virtual_machines.deletion import VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS
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

CONTAINER_READ_FIELDS = {
    "id",
    "carrier_type",
    "carrier_id",
    "name",
    "image",
    "cpu",
    "memory",
    "owner",
    "created_at",
    "updated_at",
}

CONTAINER_TABLE_COLUMNS = {
    "id",
    "bare_metal_id",
    "virtual_machine_id",
    "name",
    *OPTIONAL_FIELDS,
    "created_at",
    "updated_at",
    "deleted_at",
}

#: 容器模块源码与全部 OpenAPI path 都不得出现的越界 token（架构 §7）。
#: 注意：``container`` 自身**不**在此集合（本模块即 Container）；它仅从全局
#: ``BOUNDARY_TOKENS`` 中移除。
FORBIDDEN_MODULE_TOKENS = (
    "kubernetes",
    "k8s",
    "docker",
    "pod",
    "deployment",
    "daemonset",
    "replicaset",
    "statefulset",
    "container_runtime",
    "runtime_api",
    "data_center",
    "datacenter",
    "location",
    "room",
    "rack",
    "u_position",
    "site",
    "campus",
)

#: 集群维度 token：容器模块源码、列、OpenAPI 参数均不得出现。
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


def _openapi() -> dict:
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    return app.openapi()


# --------------------------------------------------------------------------- #
# G-1：字段封闭（契约 §2；恰 10 字段）
# --------------------------------------------------------------------------- #
def test_g1_container_read_schema_is_closed():
    from app.containers.schemas import ContainerRead

    assert set(ContainerRead.model_fields) == CONTAINER_READ_FIELDS
    assert "deleted_at" not in ContainerRead.model_fields
    assert "status" not in ContainerRead.model_fields
    assert "bare_metal_id" not in ContainerRead.model_fields
    assert "virtual_machine_id" not in ContainerRead.model_fields
    for token in FORBIDDEN_CLUSTER_TOKENS:
        assert token not in ContainerRead.model_fields


def test_g1_create_and_update_schemas_closed():
    from app.containers.schemas import ContainerCreate, ContainerUpdate

    assert ContainerCreate.model_config.get("extra") == "forbid"
    assert ContainerUpdate.model_config.get("extra") == "forbid"

    assert set(ContainerCreate.model_fields) == {
        "carrier_type",
        "carrier_id",
        "name",
        *OPTIONAL_FIELDS,
    }
    assert set(ContainerUpdate.model_fields) == set(OPTIONAL_FIELDS)
    for forbidden in (
        "id",
        "name",
        "carrier_type",
        "carrier_id",
        "bare_metal_id",
        "virtual_machine_id",
        "deleted_at",
        "status",
        "cluster_id",
    ):
        assert forbidden not in ContainerUpdate.model_fields, forbidden


# --------------------------------------------------------------------------- #
# G-2：ORM 元数据列集合恰为 11 列；无 status / 集群维度列 / 载体判别列
# --------------------------------------------------------------------------- #
def test_g2_model_metadata_columns_exact():
    from app.db.base import Base

    columns = {column.name for column in Base.metadata.tables["containers"].columns}
    assert columns == CONTAINER_TABLE_COLUMNS
    assert "status" not in columns
    assert "state" not in columns
    assert "carrier_type" not in columns
    for token in FORBIDDEN_CLUSTER_TOKENS:
        assert token not in columns


def test_g2_model_indexes_and_fk():
    from app.db.base import Base

    table = Base.metadata.tables["containers"]
    index_names = {index.name for index in table.indexes}
    assert index_names == {
        "ux_containers_bare_metal_name_active",
        "ux_containers_virtual_machine_name_active",
        "ix_containers_bare_metal_id",
        "ix_containers_virtual_machine_id",
    }
    for name in (
        "ux_containers_bare_metal_name_active",
        "ux_containers_virtual_machine_name_active",
    ):
        index = next(index for index in table.indexes if index.name == name)
        assert index.unique is True

    fks = {fk.name: fk for fk in table.foreign_keys}
    assert set(fks) == {"fk_containers_bare_metal", "fk_containers_virtual_machine"}
    for fk in fks.values():
        assert fk.ondelete == "RESTRICT"
        assert fk.onupdate == "RESTRICT"

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert set(checks) == {"ck_containers_carrier_exactly_one"}
    assert "num_nonnulls" in checks["ck_containers_carrier_exactly_one"]


# --------------------------------------------------------------------------- #
# G-3：无状态 / 无集群维度（OpenAPI 容器端点无对应 query 参数）
# --------------------------------------------------------------------------- #
def test_g3_openapi_container_endpoints_have_no_status_or_cluster_params():
    paths = _openapi()["paths"]
    for path, operations in paths.items():
        if not path.startswith("/api/containers"):
            continue
        assert "status" not in path.lower()
        for operation in operations.values():
            names = {p.get("name") for p in operation.get("parameters", [])}
            for name in names:
                assert "status" not in (name or "").lower()
                for token in FORBIDDEN_CLUSTER_TOKENS:
                    assert token not in (name or "").lower()


# --------------------------------------------------------------------------- #
# G-4：无 K8s / Docker / 运行时 / 位置字段（全部 OpenAPI path + 容器模块源码）
# --------------------------------------------------------------------------- #
def test_g4_no_forbidden_tokens_in_any_openapi_path():
    offenders = [
        path
        for path in _openapi()["paths"]
        if any(token in path.lower() for token in FORBIDDEN_MODULE_TOKENS)
    ]
    assert offenders == [], f"不得注册越界端点：{offenders}"


def test_g4_no_forbidden_tokens_in_container_module_source():
    module_dir = APP_DIR / "containers"
    offenders: list[str] = []
    for path in sorted(module_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_MODULE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert offenders == [], f"容器模块不得出现越界字段 token：{offenders}"


def test_g4_no_cluster_tokens_in_container_module_source():
    module_dir = APP_DIR / "containers"
    offenders: list[str] = []
    for path in sorted(module_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_CLUSTER_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert offenders == [], f"容器模块不得出现集群维度 token：{offenders}"


# --------------------------------------------------------------------------- #
# G-5：未定义约束「不实现」
# --------------------------------------------------------------------------- #
def test_g5_container_schemas_have_no_undefined_constraints():
    from app.containers.schemas import ContainerCreate, ContainerUpdate

    for model in (ContainerCreate, ContainerUpdate):
        for field in OPTIONAL_FIELDS:
            assert _field_constraint_flags(model, field) == set(), f"{model.__name__}.{field}"
        decorators = model.__pydantic_decorators__
        assert decorators.validators == {}
        assert decorators.field_validators == {}
    for field in ("name", *OPTIONAL_FIELDS):
        assert _field_constraint_flags(ContainerCreate, field) == set(), field


# --------------------------------------------------------------------------- #
# G-6：EXPECTED_GET_ROUTES 追加两条（只增不删）
# --------------------------------------------------------------------------- #
def test_g6_expected_get_routes_contains_container_routes():
    from tests.test_auth_guards import EXPECTED_GET_ROUTES

    assert "/api/containers" in EXPECTED_GET_ROUTES
    assert "/api/containers/{container_id}" in EXPECTED_GET_ROUTES


# --------------------------------------------------------------------------- #
# G-7：BOUNDARY_TOKENS 仅移除 container、保留 service、全局扫描不收窄
# --------------------------------------------------------------------------- #
def test_g7_boundary_tokens_narrowed_but_global():
    from tests import test_cluster_views_guards as cv

    tokens = cv.BOUNDARY_TOKENS
    assert "container" not in tokens
    assert "service" in tokens

    source = (REPO_ROOT / "tests/test_cluster_views_guards.py").read_text(encoding="utf-8")
    assert '_openapi()["paths"]' in source
    assert 'for path in _openapi()["paths"]' in source


# --------------------------------------------------------------------------- #
# G-8：唯一软删写入路径 allow-list 不变；容器模块不写 deleted_at
# --------------------------------------------------------------------------- #
def test_g8_deleted_at_writer_allowlist_unchanged():
    writers = {str(path.relative_to(REPO_ROOT)) for path in scan_deleted_at_writes()}
    assert writers == {ALLOWED_DELETED_AT_WRITER}, f"写入 deleted_at 的文件集合异常：{writers}"


def test_g8_container_module_writes_no_deleted_at():
    assert scan_deleted_at_writes(APP_DIR / "containers") == {}


# --------------------------------------------------------------------------- #
# G-9：无通用表 / EAV / JSON(B) / 多态 / ORM 继承（对 containers 成立）
# --------------------------------------------------------------------------- #
def test_g9_no_generic_eav_json_or_polymorphic_for_container():
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import configure_mappers

    from app.db.base import Base

    table = Base.metadata.tables["containers"]
    for column in table.columns:
        assert not isinstance(column.type, (JSON, JSONB)), column.name
    assert table.name != "resources"
    assert not table.name.startswith("resource_")

    configure_mappers()
    offenders = [m.class_.__name__ for m in Base.registry.mappers if m.polymorphic_on is not None]
    assert offenders == []
    inherits = [m.class_.__name__ for m in Base.registry.mappers if m.inherits is not None]
    assert inherits == []


# --------------------------------------------------------------------------- #
# G-10：活跃子检查点（BM 含 Container；VM 非空含 Container；Container 显式空）
# --------------------------------------------------------------------------- #
def test_g10_active_child_checks_are_wired():
    assert isinstance(BARE_METAL_ACTIVE_CHILD_CHECKS, tuple)
    assert BARE_METAL_ACTIVE_CHILD_CHECKS, "BareMetal 删除守卫不得 fail-open 为空"
    assert has_active_containers_on_bare_metal in BARE_METAL_ACTIVE_CHILD_CHECKS

    assert isinstance(VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS, tuple)
    assert VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS, "F007 后 VM 删除守卫不得为空"
    assert has_active_containers_on_virtual_machine in VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS

    assert isinstance(CONTAINER_ACTIVE_CHILD_CHECKS, tuple)
    assert CONTAINER_ACTIVE_CHILD_CHECKS == ()
    source = (REPO_ROOT / "backend/app/containers/deletion.py").read_text(encoding="utf-8")
    assert "CONTAINER_ACTIVE_CHILD_CHECKS" in source
    assert "= ()" in source, "必须显式声明空元组，而非隐式缺省"


def test_g10_delete_paths_consume_declared_checks():
    for module, constant in (
        ("containers", "CONTAINER_ACTIVE_CHILD_CHECKS"),
        ("bare_metals", "BARE_METAL_ACTIVE_CHILD_CHECKS"),
        ("virtual_machines", "VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS"),
    ):
        source = (REPO_ROOT / f"backend/app/{module}/service.py").read_text(encoding="utf-8")
        assert "soft_delete(" in source, f"{module} 删除必须委托统一软删服务"
        assert constant in _soft_delete_active_children_args(source), (
            f"{module} 删除必须通过 active_children= 关键字真实传入声明的活跃子检查"
        )


def test_g10_cluster_checks_not_weakened():
    # 集群删除守卫仍含「活跃 BareMetal」检查（本 Feature 未削弱）。
    from app.bare_metals.deletion import has_active_bare_metals

    assert CLUSTER_ACTIVE_CHILD_CHECKS
    assert has_active_bare_metals in CLUSTER_ACTIVE_CHILD_CHECKS


# --------------------------------------------------------------------------- #
# G-11：交付面封闭（恰 5 个端点）
# --------------------------------------------------------------------------- #
def test_g11_container_router_registers_exactly_five_endpoints():
    routes = {
        (method, route.path) for route in containers_router.routes for method in route.methods
    }
    assert routes == {
        ("POST", "/containers"),
        ("GET", "/containers"),
        ("GET", "/containers/{container_id}"),
        ("PATCH", "/containers/{container_id}"),
        ("DELETE", "/containers/{container_id}"),
    }


def test_g11_no_out_of_scope_container_routes_or_params():
    paths = _openapi()["paths"]
    forbidden_tokens = ("restore", "undelete", "purge", "trash", "batch", "by-name")
    offenders = [
        path
        for path in paths
        if path.startswith("/api/containers")
        and any(token in path.lower() for token in forbidden_tokens)
    ]
    assert offenders == [], f"不存在恢复 / 批量 / by-name 端点：{offenders}"

    list_op = paths["/api/containers"]["get"]
    param_names = {p.get("name") for p in list_op.get("parameters", [])}
    assert not any("deleted" in (name or "").lower() for name in param_names)
    assert not any("include" in (name or "").lower() for name in param_names)


# --------------------------------------------------------------------------- #
# G-12：migration head / revision chain
# --------------------------------------------------------------------------- #
def test_g12_migration_head_is_0007():
    from tests.database.helpers import MIGRATION_HEAD

    assert MIGRATION_HEAD == "0007_f007_containers"
    migration = REPO_ROOT / "backend" / "migrations" / "versions" / "0007_f007_containers.py"
    source = migration.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0006_f005_ip_addresses"' in source


# --------------------------------------------------------------------------- #
# G-13：无 CASCADE / 无触发器 / 无 lower()（ORM 侧；DB 侧另有 database guard）
# --------------------------------------------------------------------------- #
def test_g13_no_cascade_in_orm():
    from app.db.base import Base

    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.ondelete != "CASCADE", f"{table.name}.{fk.name}"


def test_g13_containers_module_has_no_lower_or_collate():
    module_dir = APP_DIR / "containers"
    # ORM 模型 / migration 不在 containers 目录，单独检查。
    sources = [path.read_text(encoding="utf-8") for path in module_dir.rglob("*.py")]
    sources.append((APP_DIR / "models" / "container.py").read_text(encoding="utf-8"))
    sources.append(
        (REPO_ROOT / "backend/migrations/versions/0007_f007_containers.py").read_text(
            encoding="utf-8"
        )
    )
    for source in sources:
        lowered = source.lower()
        # 只看真实代码用法（文档提及 ``COLLATE`` 不算）。
        assert "collate=" not in lowered
        assert "func.lower" not in lowered
        assert ".lower(" not in lowered


# --------------------------------------------------------------------------- #
# G-14：ORM 元数据无第二条写 deleted_at 的路径（模型不含写入）
# --------------------------------------------------------------------------- #
def test_g14_container_model_does_not_define_delete_helper():
    from app.db.base import Base

    # 容器模块源码不得出现 undelete（deleted_at = None 等）。
    from tests.deletion_guard_helpers import scan_undelete_writes

    assert scan_undelete_writes(APP_DIR / "containers") == []
    assert "containers" in Base.metadata.tables
