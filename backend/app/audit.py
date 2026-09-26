"""审计写入接口（架构 §2.3 / ADR-005）。

append-only：本模块只 INSERT，不做 UPDATE/DELETE。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog
from .security.principal import Principal

SYSTEM_ACTOR = "system"


def write(
    db: Session,
    actor: Principal | None,
    action: str,
    target_type: str,
    target_id: str | None,
    target_key_snapshot: str | None,
    change: dict[str, Any] | None,
    result: str = "success",
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor.user_id if actor is not None else None,
        actor_username_snapshot=actor.username if actor is not None else SYSTEM_ACTOR,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_key_snapshot=target_key_snapshot,
        change=change or {},
        result=result,
    )
    db.add(entry)
    return entry