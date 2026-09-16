"""BareMetal 领域校验 —— **唯一一份**实现，``POST`` / ``PATCH`` 共用。

职责（F002 REQUIRED #5）：

- ``status`` 取值必须是**封闭集合** ``{IDLE, ALLOC, DOWN, UNKNOWN}``
  （R-BM-003）；否则 ``400 VALIDATION_ERROR`` + ``details[].field = "status"``。
- ``None`` / 空串 / ``RUNNING`` / ``idle`` 一律拒绝（R-BM-005：不得以 ``NULL``
  代替 ``UNKNOWN``）；数据库 ``ck_bare_metals_status`` 为最终权威，预检被绕过时
  ``23514`` 经通用映射同样返回 ``400``（**永不返回 500**）。

**不实现**任何 ``hostname`` 字符 / 长度 / trim 校验（假设 5 / NQ-4 未定义约束）。
"""

from __future__ import annotations

from app.common.errors import ValidationError

#: R-BM-003：状态封闭集合。不得新增 / 合并 / 重命名。
STATUS_VALUES: frozenset[str] = frozenset({"IDLE", "ALLOC", "DOWN", "UNKNOWN"})

#: R-BM-004：新建默认状态。
DEFAULT_STATUS = "IDLE"


def validate_status(status: str | None) -> None:
    """校验状态值属于封闭集合；``None`` / 非法值 → ``400 VALIDATION_ERROR``。"""
    if status not in STATUS_VALUES:
        raise ValidationError(
            "状态值非法",
            details=[
                {
                    "field": "status",
                    "code": "INVALID",
                    "message": "状态必须是 IDLE / ALLOC / DOWN / UNKNOWN 之一",
                }
            ],
        )
