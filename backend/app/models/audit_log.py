"""``audit_logs`` model (DB-D27..DB-D29).

Append-only audit trail (enforced at the database level by
``trg_audit_logs_append_only``). There is no ``deleted_at``/``version`` and this
model must NOT inherit ``SoftDeleteMixin``. ``object_type``/``object_id`` are
polymorphic without an object FK so audit survives object deletion/restore and
name reuse (§21/§22); ``operator_user_id`` is an FK to ``users.id`` with
``ON DELETE RESTRICT`` while ``operator_username`` keeps the historical identity
snapshot.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    operator_username: Mapped[str] = mapped_column(String(64), nullable=False)
    # F017/DR-306: snapshot of the operator's API Key label (NULL for Cookie /
    # system paths). No FK — it must survive Key revocation/account disable and
    # mirrors the ``operator_username`` snapshot semantics.
    api_key_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    before_data: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    after_data: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "btrim(operator_username) <> ''",
            name="operator_username_not_blank",
        ),
        CheckConstraint(
            "api_key_label IS NULL OR btrim(api_key_label) <> ''",
            name="api_key_label_not_blank",
        ),
        CheckConstraint(
            "action IN ('CREATE','UPDATE','DELETE','RESTORE')", name="action"
        ),
        CheckConstraint(
            "before_data IS NOT NULL OR after_data IS NOT NULL",
            name="at_least_one_snapshot",
        ),
        CheckConstraint(
            "before_data IS NULL OR jsonb_typeof(before_data) = 'object'",
            name="before_data_object",
        ),
        CheckConstraint(
            "after_data IS NULL OR jsonb_typeof(after_data) = 'object'",
            name="after_data_object",
        ),
        Index(
            "ix_audit_logs_object_type_object_id",
            "object_type",
            "object_id",
            "created_at",
        ),
        Index("ix_audit_logs_operator_user_id", "operator_user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<AuditLog id={self.id!r} action={self.action!r} "
            f"object_type={self.object_type!r} object_id={self.object_id!r}>"
        )