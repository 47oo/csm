"""VirtualMachine 请求 / 响应 schema（``docs/api/f006-virtual-machine.md`` §2 / §3）。

- ``VirtualMachineRead``：字段集合**恰为** ``{id, bare_metal_id, name, cpu, memory,
  disk, os, hypervisor, owner, created_at, updated_at}``（11 字段）：**无**
  ``deleted_at`` / ``status`` / ``cluster_id``，也无 NIC / 位置 / 平台接入字段。
- ``VirtualMachineCreate``：``bare_metal_id`` / ``name`` 必填，R-VM-006 六字段可选。
  ``name`` **无** ``min_length`` / ``max_length`` / ``pattern`` / ``str_strip_whitespace``，
  也不做归一化（假设 6 / NQ-5 未定义约束「不实现」）。请求 schema **封闭**
  （``extra="forbid"``）：未识别字段 → ``400``（契约 §3.1）。
- ``VirtualMachineUpdate``：仅 R-VM-006 六个可选字段；**不含** ``name`` /
  ``bare_metal_id`` / ``id`` / ``deleted_at`` / ``status``；``extra="forbid"``。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

#: R-VM-006 六个可选字段（纯文本，允许 NULL，不结构化）。
OPTIONAL_FIELDS: tuple[str, ...] = ("cpu", "memory", "disk", "os", "hypervisor", "owner")


class VirtualMachineCreate(BaseModel):
    """``POST /api/virtual-machines`` 请求体（请求 schema 封闭）。"""

    model_config = ConfigDict(extra="forbid")

    bare_metal_id: int
    name: str
    cpu: str | None = None
    memory: str | None = None
    disk: str | None = None
    os: str | None = None
    hypervisor: str | None = None
    owner: str | None = None


class VirtualMachineUpdate(BaseModel):
    """``PATCH /api/virtual-machines/{virtual_machine_id}`` 请求体（部分更新）。

    ``extra="forbid"``：``name`` / ``bare_metal_id`` / ``id`` / ``deleted_at`` /
    ``status`` 或任何未识别字段 → ``400 VALIDATION_ERROR``。
    """

    model_config = ConfigDict(extra="forbid")

    cpu: str | None = None
    memory: str | None = None
    disk: str | None = None
    os: str | None = None
    hypervisor: str | None = None
    owner: str | None = None


class VirtualMachineRead(BaseModel):
    """单个 VirtualMachine 的对外表示（契约 §2 的封闭字段集合，恰 11 字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bare_metal_id: int
    name: str
    cpu: str | None
    memory: str | None
    disk: str | None
    os: str | None
    hypervisor: str | None
    owner: str | None
    created_at: datetime
    updated_at: datetime
