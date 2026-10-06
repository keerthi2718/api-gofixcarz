import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AdminAuditLog(Base):
    """Append-only application log; never store tokens, OTPs or request bodies."""
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        CheckConstraint("(actor_id IS NULL) <> (admin_account_id IS NULL)", name="ck_admin_audit_logs_one_actor"),
        Index("ix_admin_audit_logs_admin_account_id", "admin_account_id"),
        Index("ix_admin_audit_logs_created_at", "created_at"),
        Index("ix_admin_audit_logs_actor_id", "actor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
    )
    admin_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
