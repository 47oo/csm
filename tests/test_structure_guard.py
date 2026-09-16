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
    }
