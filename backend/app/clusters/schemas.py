"""Cluster 请求 / 响应 schema（docs/api/f001-cluster.md §2 / §3）。

- ``name`` 只做 Pydantic 的类型 / 必填校验；**不**加 ``min_length`` /
  ``max_length`` / ``pattern`` / ``str_strip_whitespace``，也不做 NFC 归一化。
  ``name`` 的长度 / 首尾空白 / 空字符串 / Unicode 规范化属
  ``undefined_constraints``，F001 不实现、不承诺（契约 §7、问题 8 / G1）。
- 响应字段集合**恰为** ``{id, name, created_at, updated_at}``：无 ``deleted_at``、
  无状态字段、无位置 / 上级字段（AC-01 / AC-09 / AC-10）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClusterCreate(BaseModel):
    """``POST /api/clusters`` 请求体。"""

    name: str


class ClusterUpdate(BaseModel):
    """``PATCH /api/clusters/{cluster_id}`` 请求体（``name`` 是唯一可变字段）。"""

    name: str


class ClusterRead(BaseModel):
    """单个 Cluster 的对外表示（契约 §2 的封闭字段集合）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
