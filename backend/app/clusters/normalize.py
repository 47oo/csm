"""集群 code 规范化小工具（架构 §2.1）。

``normalize_cluster_code(raw) = upper(trim(raw))``：判重与二次确认比较统一使用。
不改展示形态，不做格式以外的业务判断。
"""

from __future__ import annotations


def normalize_cluster_code(raw: str) -> str:
    return raw.strip().upper()