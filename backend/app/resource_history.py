"""受管对象资源历史写入接口（架构 §2.1 / ADR-005）。

append-only：本模块只 INSERT，不做 UPDATE/DELETE。查询 API 由 F012 交付。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import ResourceHistory
from .security.principal import Principal


def write(
    db: Session,
    actor: Principal | None,
    action: str,
    target_type: str,
    target_id: str | None,
    target_key_snapshot: str | None,
    change: dict[str, Any] | None,
) -> ResourceHistory:
    entry = ResourceHistory(
        actor_user_id=actor.user_id if actor is not None else None,
        actor_username_snapshot=actor.username if actor is not None else "system",
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_key_snapshot=target_key_snapshot,
        change=change or {},
    )
    db.add(entry)
    return entry