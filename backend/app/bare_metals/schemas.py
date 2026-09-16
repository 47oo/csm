"""BareMetal 请求 / 响应 schema（``docs/api/f002-bare-metal.md`` §2 / §3）。

- ``BareMetalRead``：字段集合**恰为** ``{id, cluster_id, hostname, status, vendor,
  model, serial_number, cpu, memory, gpu, storage, created_at, updated_at}``：
  **无** ``deleted_at``、无位置 / 上级字段。
- ``BareMetalCreate``：``cluster_id`` / ``hostname`` 必填，``status`` 可选
  （缺省由数据库默认 ``IDLE`` 生效），R-BM-007 七字段可选。``hostname`` **无**
  ``min_length`` / ``max_length`` / ``pattern`` / ``str_strip_whitespace``，也不做
  NFC 归一化（假设 5 / NQ-4 未定义约束「不实现」）。请求 schema **封闭**
  （``extra="forbid"``）：未识别字段 → ``400``（契约 §3.1）。
- ``BareMetalUpdate``：仅 ``status`` + R-BM-007 七字段；**不含** ``hostname`` /
  ``cluster_id`` / ``id`` / ``deleted_at``；``extra="forbid"``（未识别字段 → 400）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

#: R-BM-007 七个可选硬件字段（纯文本，允许 NULL；``serial_number`` 不参与唯一性）。
HARDWARE_FIELDS: tuple[str, ...] = (
    "vendor",
    "model",
    "serial_number",
    "cpu",
    "memory",
    "gpu",
    "storage",
)


class BareMetalCreate(BaseModel):
    """``POST /api/bare-metals`` 请求体（请求 schema 封闭）。"""

    model_config = ConfigDict(extra="forbid")

    cluster_id: int
    hostname: str
    status: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    cpu: str | None = None
    memory: str | None = None
    gpu: str | None = None
    storage: str | None = None


class BareMetalUpdate(BaseModel):
    """``PATCH /api/bare-metals/{bare_metal_id}`` 请求体（部分更新）。

    ``extra="forbid"``：``hostname`` / ``cluster_id`` / ``id`` / ``deleted_at`` 或任何
    未识别字段 → ``400 VALIDATION_ERROR``。
    """

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    cpu: str | None = None
    memory: str | None = None
    gpu: str | None = None
    storage: str | None = None


class BareMetalRead(BaseModel):
    """单个 BareMetal 的对外表示（契约 §2 的封闭字段集合）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cluster_id: int
    hostname: str
    status: str
    vendor: str | None
    model: str | None
    serial_number: str | None
    cpu: str | None
    memory: str | None
    gpu: str | None
    storage: str | None
    created_at: datetime
    updated_at: datetime
