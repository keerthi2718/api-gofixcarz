"""Trusted-source read models, workflow resources and immutable report snapshots."""
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base, TimestampMixin


class CustomerAccount(Base, TimestampMixin):
    __tablename__ = "customer_accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    mobile: Mapped[str | None] = mapped_column(String(30))
    account_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(100))


class AccountGarage(Base):
    __tablename__ = "customer_account_garages"
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_accounts.id"), primary_key=True)
    garage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("garages.id"), primary_key=True)


class SourceRecord(Base, TimestampMixin):
    __tablename__ = "admin_source_records"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_admin_source_external"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    source: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str] = mapped_column(String(200))
    garage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("garages.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_accounts.id"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_source_records.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class SupportMessage(Base, TimestampMixin):
    __tablename__ = "support_messages"
    __table_args__ = (UniqueConstraint("ticket_id", "sender_id", "client_message_id", name="uq_support_message_client"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_source_records.id"), index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sender_role: Mapped[str] = mapped_column(String(30), default="ADMIN")
    client_message_id: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)


class AdminResource(Base, TimestampMixin):
    """Non-domain resources: announcement previews/batches, snapshots and export jobs."""
    __tablename__ = "admin_resources"
    __table_args__ = (UniqueConstraint("actor_id", "kind", "idempotency_key", name="uq_admin_resource_idempotency"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
