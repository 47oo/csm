"""认证请求 / 响应 schema（F013，docs/api/f013-auth.md §4 / §5）。

- ``LoginRequest``：``username`` / ``password`` 均必填 ``str``。**不设**
  ``min_length``：R-AUTH-004 的校验是服务端领域层（``app.auth.policy``）的
  单一实现，不在 HTTP schema 里重复（Architecture Handoff REQUIRED #3 / G-D）。
- ``AuthenticatedUser``：字段集合封闭为 ``{id, username}``；无 ``password_hash`` /
  ``active`` / 角色 / 权限字段。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    """``POST /api/auth/login`` 请求体。"""

    username: str
    password: str


class AuthenticatedUser(BaseModel):
    """登录成功与会话校验返回的同一对象结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
