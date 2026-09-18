"""NetworkInterface 请求 / 响应 schema（``docs/api/f004-network-interface.md`` §2 / §3）。

- ``NetworkInterfaceRead``：字段集合**恰为** ``{id, bare_metal_id, name,
  technology_type, purpose, created_at, updated_at}``（7 字段）：**无**
  ``deleted_at`` / ``status`` / ``cluster_id``，也无 IP / MAC / 速率 / MTU /
  载体多态字段。
- ``NetworkInterfaceCreate``：``bare_metal_id`` / ``name`` / ``technology_type`` /
  ``purpose`` 必填。``name`` **无** ``min_length`` / ``max_length`` / ``pattern`` /
  ``str_strip_whitespace``，也不做归一化（未定义约束「不实现」）。请求 schema
  **封闭**（``extra="forbid"``）：未识别字段 → ``400``（契约 §3.1）。
- ``NetworkInterfaceUpdate``：仅 ``technology_type`` / ``purpose`` 两个可变字段；
  **不含** ``name`` / ``bare_metal_id`` / ``id`` / ``created_at`` / ``deleted_at`` /
  ``status``；``extra="forbid"``。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

#: NQ-7：PATCH 可变字段封闭集合。
MUTABLE_FIELDS: tuple[str, ...] = ("technology_type", "purpose")


class NetworkInterfaceCreate(BaseModel):
    """``POST /api/network-interfaces`` 请求体（请求 schema 封闭）。

    **不给任何字段加约束**：必填性以外的长度 / trim / 字符规则一律不实现
    （``name`` 属未定义约束；两个枚举的取值校验在 ``validation.py``）。
    """

    model_config = ConfigDict(extra="forbid")

    bare_metal_id: int
    name: str
    technology_type: str
    purpose: str


class NetworkInterfaceUpdate(BaseModel):
    """``PATCH /api/network-interfaces/{network_interface_id}`` 请求体（部分更新）。

    ``extra="forbid"``：``name`` / ``bare_metal_id`` / ``id`` / ``created_at`` /
    ``deleted_at`` / ``status`` 或任何未识别字段 → ``400 VALIDATION_ERROR``。
    """

    model_config = ConfigDict(extra="forbid")

    technology_type: str | None = None
    purpose: str | None = None


class NetworkInterfaceRead(BaseModel):
    """单个 NetworkInterface 的对外表示（契约 §2 的封闭字段集合，恰 7 字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bare_metal_id: int
    name: str
    technology_type: str
    purpose: str
    created_at: datetime
    updated_at: datetime
