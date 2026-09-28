"""Pydantic v2 Schemas（字段以 docs/api/F013.md 为准）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["viewer", "maintainer", "admin"]
UserStatus = Literal["enabled", "disabled"]


class CurrentUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    status: UserStatus
    must_change_password: bool


class UserListItemOut(CurrentUserOut):
    created_at: datetime
    updated_at: datetime


class UserDetailOut(UserListItemOut):
    version: int


class PagedUsers(BaseModel):
    items: list[UserListItemOut]
    total: int
    page: int
    page_size: int


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: Role


class UserUpdateRequest(BaseModel):
    # 仅角色可变（BQ-X）。username 等额外字段由路由层判定为 400 INVALID_REQUEST。
    model_config = ConfigDict(extra="allow")

    role: Role | None = None
    version: int


class ResetPasswordRequest(BaseModel):
    new_password: str