"""会话 token 生成与哈希。仅存 token 的 SHA-256 hex，不存明文（架构 §4.2）。"""

from __future__ import annotations

import hashlib
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()