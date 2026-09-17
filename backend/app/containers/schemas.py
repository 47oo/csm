"""Container 请求 / 响应 schema（``docs/api/f007-container.md`` §2 / §4）。

- ``ContainerRead``：字段集合**恰为** ``{id, carrier_type, carrier_id, name, image,
  cpu, memory, owner, created_at, updated_at}``（10 字段）：**无** ``deleted_at``，
  也不暴露 ``bare_metal_id`` / ``virtual_machine_id`` 两个原始载体列名。
- 载体在请求 / 响应 / 查询参数中统一以 ``carrier_type``（封闭枚举
  ``BARE_METAL`` | ``VIRTUAL_MACHINE``）+ ``carrier_id`` 表达。
- ``ContainerCreate``：``carrier_type`` / ``carrier_id`` / ``name`` 必填，
  ``image`` / ``cpu`` / ``memory`` / ``owner`` 四个可选字段（R-CONTAINER-004）。
  ``name`` 与四个可选字段**无** ``min_length`` / ``max_length`` / ``pattern`` /
  ``str_strip_whitespace``，也不做归一化（未定义约束「不实现」）。请求 schema
  **封闭**（``extra="forbid"``）：未识别字段（含 ``bare_metal_id`` /
  ``virtual_machine_id`` / 集群维度 / ``status`` / ``deleted_at`` / ``id``）→ ``400``。
- ``ContainerUpdate``：仅四个可变可选字段；**不含** ``name`` / ``carrier_type`` /
  ``carrier_id`` / ``id`` / ``deleted_at``；``extra="forbid"``。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.models.container import Container


class CarrierType(StrEnum):
    """运行载体类型的封闭集合（R-CONTAINER-002）。"""

    BARE_METAL = "BARE_METAL"
    VIRTUAL_MACHINE = "VIRTUAL_MACHINE"


#: R-CONTAINER-004 四个可选字段（纯文本，允许 NULL，不结构化）。
OPTIONAL_FIELDS: tuple[str, ...] = ("image", "cpu", "memory", "owner")


def carrier_of(container: Container) -> tuple[CarrierType, int]:
    """由非空载体列派生 ``(carrier_type, carrier_id)``；不由客户端写入。"""
    if container.bare_metal_id is not None:
        return CarrierType.BARE_METAL, container.bare_metal_id
    return CarrierType.VIRTUAL_MACHINE, container.virtual_machine_id  # type: ignore[arg-type]


class ContainerCreate(BaseModel):
    """``POST /api/containers`` 请求体（请求 schema 封闭）。"""

    model_config = ConfigDict(extra="forbid")

    carrier_type: CarrierType
    carrier_id: int
    name: str
    image: str | None = None
    cpu: str | None = None
    memory: str | None = None
    owner: str | None = None


class ContainerUpdate(BaseModel):
    """``PATCH /api/containers/{container_id}`` 请求体（部分更新）。

    可变字段恰为 ``{image, cpu, memory, owner}``；``name`` 与载体绑定不可变。
    ``extra="forbid"``：任何未识别 / 不可变字段 → ``400 VALIDATION_ERROR``。
    """

    model_config = ConfigDict(extra="forbid")

    image: str | None = None
    cpu: str | None = None
    memory: str | None = None
    owner: str | None = None


class ContainerRead(BaseModel):
    """单个 Container 的对外表示（契约 §2 的封闭字段集合，恰 10 字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    carrier_type: CarrierType
    carrier_id: int
    name: str
    image: str | None
    cpu: str | None
    memory: str | None
    owner: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, container: Container) -> ContainerRead:
        """从 ORM 行构造对外表示，``carrier_type`` / ``carrier_id`` 由非空列派生。"""
        carrier_type, carrier_id = carrier_of(container)
        return cls(
            id=container.id,
            carrier_type=carrier_type,
            carrier_id=carrier_id,
            name=container.name,
            image=container.image,
            cpu=container.cpu,
            memory=container.memory,
            owner=container.owner,
            created_at=container.created_at,
            updated_at=container.updated_at,
        )
