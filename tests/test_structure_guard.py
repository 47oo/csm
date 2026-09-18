"""T10 — 结构 guard：无通用 resources 表 / EAV / STI / 多态 mapper / JSON(JSONB) 列。

把 §4 / §24 / §25 的产品规则变成会失败的测试，而非仅靠文档约定。
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401  (注册全部模型)
from app.db.base import Base

JSON_TYPES = (JSON, JSONB)


def test_no_generic_resources_table():
    for table_name in Base.metadata.tables:
        assert table_name != "resources", f"禁止通用表：{table_name}"
        assert not table_name.startswith("resource_"), f"禁止通用表：{table_name}"


def test_no_json_or_jsonb_columns():
    offenders = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSON_TYPES):
                offenders.append(f"{table.name}.{column.name}")
    assert offenders == [], f"禁止 JSON / JSONB 列：{offenders}"


def test_no_polymorphic_mappers_or_discriminator():
    configure_mappers()
    offenders = []
    for mapper in Base.registry.mappers:
        if mapper.polymorphic_on is not None:
            offenders.append(mapper.class_.__name__)
    assert offenders == [], f"禁止 ORM 多态映射：{offenders}"


def test_no_orm_inheritance_at_all():
    """STI / joined inheritance 都必须不存在：本项目不建立 ORM 继承层次。"""
    configure_mappers()
    offenders = [m.class_.__name__ for m in Base.registry.mappers if m.inherits is not None]
    assert offenders == [], f"禁止 ORM 继承（含 STI）：{offenders}"


def test_no_eav_shape():
    """禁止 EAV 形态：{'attribute'/'key' 列 + 通用 owner FK + 'value' 列}。"""
    eav_indicators = {"attribute", "attribute_name", "attr_name", "key", "attr_key"}
    value_indicators = {"value", "attr_value", "attribute_value"}
    owner_prefixes = ("owner", "entity", "resource", "subject")
    for table in Base.metadata.tables.values():
        columns = {c.name for c in table.columns}
        if columns & eav_indicators and columns & value_indicators:
            if any(c.startswith(owner_prefixes) for c in columns):
                raise AssertionError(f"疑似 EAV 表：{table.name}")


def test_only_expected_tables_registered():
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
    }


#: 已批准的产品资源路径前缀（``/api`` 下的首段）。新增 Feature 时**追加**。
APPROVED_API_PREFIXES = {
    "health",
    "auth",
    "clusters",
    "bare-metals",
    "virtual-machines",
    "network-interfaces",
    "ip-addresses",
    # F007：Container 资源端点。
    "containers",
    # F008：Service 资源端点。
    "services",
}


def test_product_api_surface_is_closed():
    """交付面封闭：``/api`` 下每个 path 的首段必须属于已批准资源前缀。

    该 allowlist 比 ``BOUNDARY_TOKENS`` 的 denylist 更强：它使任何未批准的
    新资源端点（如 ``/api/vpns`` / ``/api/containers``）都会被检出。
    """
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    offenders = []
    for path in app.openapi()["paths"]:
        assert path.startswith("/api"), path
        first = path[len("/api/") :].split("/", 1)[0]
        if first not in APPROVED_API_PREFIXES:
            offenders.append(path)
    assert offenders == [], f"不得注册未批准资源端点：{offenders}"
