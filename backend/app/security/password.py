"""口令哈希与策略（架构 §4.3）。

策略：长度 ≥ 8 且同时含至少一个 ASCII 英文字母与一个数字。
"""

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # 默认 Argon2id

_ASCII_LETTER = re.compile(r"[A-Za-z]")
_DIGIT = re.compile(r"[0-9]")

PASSWORD_POLICY_MESSAGE = "口令至少 8 位且同时包含字母与数字"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_policy_ok(password: str) -> bool:
    return (
        isinstance(password, str)
        and len(password) >= 8
        and bool(_ASCII_LETTER.search(password))
        and bool(_DIGIT.search(password))
    )