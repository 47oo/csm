"""口令策略（F013，R-AUTH-004）。

本模块是全项目**唯一**的口令长度校验实现（G-D 静态 guard 固定这一点）。
HTTP schema、前端、CLI 都不得另写一份。

规则：口令长度**至少 8 位**。低于 8 位不得被接受。除长度下限外 V1 不对口令
提出任何其他强度要求（不要求大小写混合 / 数字 / 符号，也不做弱口令黑名单）。

失败抛 ``ValidationError``（统一错误信封的 400 语义）。错误信息**不得**回显
口令值。
"""

from __future__ import annotations

from app.common.errors import ValidationError

MIN_PASSWORD_LENGTH = 8

_ERROR_MESSAGE = f"口令长度至少 {MIN_PASSWORD_LENGTH} 位"


def validate_password(password: str) -> None:
    """校验口令是否满足 R-AUTH-004；不满足则抛 ``ValidationError``。"""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            _ERROR_MESSAGE,
            details=[
                {
                    "field": "password",
                    "code": "TOO_SHORT",
                    # 只描述规则，绝不回显口令值。
                    "message": _ERROR_MESSAGE,
                }
            ],
        )
