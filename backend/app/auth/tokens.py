"""会话令牌生成与哈希（F013，ADR-0005 §3）。

- 令牌：256-bit 随机不可预测不透明值，URL-safe base64（``secrets.token_urlsafe``）。
- 存储：数据库只保存其 SHA-256 hex 摘要；token 原文不落库。

令牌为高熵随机值、无字典风险，因此无需慢哈希（Architecture Handoff PROPOSED-2）。
"""

from __future__ import annotations

import hashlib
import secrets

#: 256-bit 熵。
TOKEN_BYTES = 32


def generate_session_token() -> str:
    """生成新的会话令牌（URL-safe base64 字符串）。"""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """返回会话令牌的 SHA-256 十六进制摘要。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
