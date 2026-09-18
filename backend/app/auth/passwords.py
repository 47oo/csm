"""Argon2id 口令哈希（F013，ADR-0005 §2）。

本模块是全项目**唯一**的 Argon2 使用点（G-D 静态 guard 固定这一点）。

参数为**实现常量**（非环境变量），对应 Architecture Handoff PROPOSED-1：
``memory_cost=65536 KiB (64 MiB)`` / ``time_cost=3`` / ``parallelism=1`` /
``hash_len=32`` / ``salt_len=16``。

安全约束：

- 明文口令只作为函数入参存在，**不落库、不落日志、不落错误信息**；
- 用户不存在时，调用方使用 ``verify_dummy`` 执行一次等价 Argon2 校验，避免以
  耗时区分「用户名不存在」与「口令错误」（R-AUTH-006）。
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

# 进程内常量 dummy hash：仅用于「用户不存在」时执行一次等价耗时的校验。
# 明文与最终 ``users.password_hash`` 无关，且从未被写出到任何地方。
_DUMMY_HASH = _PASSWORD_HASHER.hash("csm-dummy-password-timing-equalizer")

# 校验失败一律返回 False；不向外抛出可区分原因的异常。
_VERIFY_ERRORS = (VerifyMismatchError, VerificationError, InvalidHashError)


def hash_password(password: str) -> str:
    """返回 Argon2id 哈希字符串（``$argon2id$...``）。"""
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """校验明文口令是否匹配已存哈希。

    任何失败（不匹配 / 哈希损坏 / 算法不可用）都返回 ``False``，不泄露原因，
    也不在异常信息中出现明文。
    """
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except _VERIFY_ERRORS:
        return False


def verify_dummy(password: str) -> None:
    """对常量 dummy hash 执行一次等价耗时的校验。

    用于「用户名不存在」分支，使登录失败的响应耗时与「口令错误」分支无法区分。
    结果被丢弃；本函数永不抛出。
    """
    try:
        _PASSWORD_HASHER.verify(_DUMMY_HASH, password)
    except _VERIFY_ERRORS:
        return
