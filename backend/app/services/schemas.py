"""Service 请求 / 响应 schema（``docs/api/f008-service.md`` §2 / §4）。

- ``ServiceCarrierType``：运行载体类型的**封闭三值集合**（``BARE_METAL`` |
  ``VIRTUAL_MACHINE`` | ``CONTAINER``，词汇与 F007 一致并扩展 ``CONTAINER``）。
- ``CarrierRef``：载体身份 = ``(carrier_type, carrier_id)`` 二元组；``extra="forbid"``。
- ``ServiceCreate``：``name`` 必填；``carriers`` 必填且 ``min_length=1``（R-SVC-005）；
  6 个可选字段（``service_type`` / ``url`` / ``port`` / ``protocol`` / ``owner`` /
  ``description``）。``name`` 与 6 个字段**无** ``min_length`` / ``max_length`` /
  ``pattern`` / ``str_strip_whitespace``，也不做归一化（AC-15 未定义约束不实现）。
- ``ServiceUpdate``：**恰 6 个**可变可选字段；**不含** ``name`` / ``carriers`` /
  ``carrier_type`` / ``carrier_id`` / ``id`` / ``deleted_at``（NQ-01 / NQ-02）。
- ``ServiceRead``：封闭字段集合，**恰 11 字段**（含 ``carriers``），不暴露
  ``deleted_at`` / ``status`` / 集群维度字段 / 原始载体列名。

``carriers`` 的顺序稳定性（契约级保证）：响应中的 ``carriers`` 恒按
``(carrier_type rank, carrier_id)`` 升序，``rank = BARE_METAL < VIRTUAL_MACHINE <
CONTAINER``；该顺序不依赖请求 / 插入 / 数据库行序。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.service import Service

#: R-SVC-001 / R-SVC-007：6 个可选字段（纯文本，允许 NULL，不结构化）。
OPTIONAL_FIELDS: tuple[str, ...] = (
    "service_type",
    "url",
    "port",
    "protocol",
    "owner",
    "description",
)


class ServiceCarrierType(StrEnum):
    """运行载体类型的封闭三值集合。"""

    BARE_METAL = "BARE_METAL"
    VIRTUAL_MACHINE = "VIRTUAL_MACHINE"
    CONTAINER = "CONTAINER"


#: 单一全序（与登记加锁协议 §3、响应顺序 §2 共用）：BARE_METAL < VIRTUAL_MACHINE < CONTAINER。
CARRIER_RANK: dict[ServiceCarrierType, int] = {
    ServiceCarrierType.BARE_METAL: 0,
    ServiceCarrierType.VIRTUAL_MACHINE: 1,
    ServiceCarrierType.CONTAINER: 2,
}


class CarrierRef(BaseModel):
    """载体身份二元组（封闭，恰 2 字段）。"""

    model_config = ConfigDict(extra="forbid")

    carrier_type: ServiceCarrierType
    carrier_id: int


class ServiceCreate(BaseModel):
    """``POST /api/services`` 请求体（请求 schema 封闭）。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    carriers: list[CarrierRef] = Field(min_length=1)
    service_type: str | None = None
    url: str | None = None
    port: str | None = None
    protocol: str | None = None
    owner: str | None = None
    description: str | None = None


class ServiceUpdate(BaseModel):
    """``PATCH /api/services/{service_id}`` 请求体（部分更新）。

    可变字段恰为 6 个；``name`` 与载体绑定不可变（NQ-01 / NQ-02）。
    ``extra="forbid"``：任何未识别 / 不可变字段 → ``400 VALIDATION_ERROR``。
    """

    model_config = ConfigDict(extra="forbid")

    service_type: str | None = None
    url: str | None = None
    port: str | None = None
    protocol: str | None = None
    owner: str | None = None
    description: str | None = None


class ServiceRead(BaseModel):
    """单个 Service 的对外表示（契约 §2 的封闭字段集合，恰 11 字段）。"""

    id: int
    name: str
    service_type: str | None
    url: str | None
    port: str | None
    protocol: str | None
    owner: str | None
    description: str | None
    carriers: list[CarrierRef]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, service: Service, carriers: list[CarrierRef]) -> ServiceRead:
        """从 ORM 行与已装配 / 已排序的载体列表构造对外表示。"""
        return cls(
            id=service.id,
            name=service.name,
            service_type=service.service_type,
            url=service.url,
            port=service.port,
            protocol=service.protocol,
            owner=service.owner,
            description=service.description,
            carriers=carriers,
            created_at=service.created_at,
            updated_at=service.updated_at,
        )


__all__ = [
    "CARRIER_RANK",
    "OPTIONAL_FIELDS",
    "CarrierRef",
    "ServiceCarrierType",
    "ServiceCreate",
    "ServiceRead",
    "ServiceUpdate",
]
