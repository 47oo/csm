"""NetworkInterface 领域校验 —— **唯一一份**实现，``POST`` / ``PATCH`` 共用。

职责（F004 决策 6 / REQUIRED #7）：

- ``technology_type`` 取值必须是**封闭集合** ``{Ethernet, InfiniBand, RoCE, Other}``
  （R-NIC-001）；否则 ``400 VALIDATION_ERROR`` + ``details[].field`` +
  ``details[].code = "INVALID"``。
- ``purpose`` 取值必须是**封闭集合** ``{BMC, Management, Business, Compute,
  Storage, DataTransfer, Other}``（R-NIC-002）；语义同上。
- 字面精确匹配：**不做**大小写折叠 / ``trim`` / NFC 归一 / 中文映射。
- 数据库 ``CHECK`` 为最终权威；绕过应用层直写非法值 ``23514`` 经通用映射同样返回
  ``400``（**永不返回 500**）。

**不实现**任何 ``name`` 的字符 / 长度 / trim / 空串校验（NQ-8 未定义约束）。
"""

from __future__ import annotations

from app.common.errors import ValidationError

#: R-NIC-001：技术类型封闭集合。不得新增 / 合并 / 重命名。
TECHNOLOGY_TYPE_VALUES: frozenset[str] = frozenset({"Ethernet", "InfiniBand", "RoCE", "Other"})

#: R-NIC-002：用途封闭集合。不得新增 / 合并 / 重命名。
PURPOSE_VALUES: frozenset[str] = frozenset(
    {"BMC", "Management", "Business", "Compute", "Storage", "DataTransfer", "Other"}
)


def validate_technology_type(value: str | None) -> None:
    """校验 ``technology_type`` 属于封闭集合；``None`` / 非法值 → ``400``。"""
    if value not in TECHNOLOGY_TYPE_VALUES:
        raise ValidationError(
            "技术类型值非法",
            details=[
                {
                    "field": "technology_type",
                    "code": "INVALID",
                    "message": "技术类型必须是 Ethernet / InfiniBand / RoCE / Other 之一",
                }
            ],
        )


def validate_purpose(value: str | None) -> None:
    """校验 ``purpose`` 属于封闭集合；``None`` / 非法值 → ``400``。"""
    if value not in PURPOSE_VALUES:
        raise ValidationError(
            "用途值非法",
            details=[
                {
                    "field": "purpose",
                    "code": "INVALID",
                    "message": (
                        "用途必须是 BMC / Management / Business / Compute / "
                        "Storage / DataTransfer / Other 之一"
                    ),
                }
            ],
        )
