"""Dedicated platform identities; never garage-owner signups."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class AdminAccount(Base, TimestampMixin):
    __tablename__ = "admin_accounts"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_admin_accounts_email_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def role(self) -> str:
        return "admin"


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_accounts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
