"""Customer-owned resources; legacy garage contacts are never ownership proofs."""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base, TimestampMixin


class CustomerVehicle(Base, TimestampMixin):
    __tablename__ = "customer_app_vehicles"
    __table_args__ = (
        Index("uq_customer_active_registration", "customer_id", "registration_number",
              unique=True, postgresql_where=text("archived_at IS NULL")),
        Index("uq_customer_default_vehicle", "customer_id", unique=True,
              postgresql_where=text("is_default AND archived_at IS NULL")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    registration_number: Mapped[str] = mapped_column(String(20))
    brand: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    fuel_type: Mapped[str] = mapped_column(String(20))
    year: Mapped[int | None] = mapped_column(Integer)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerAttachment(Base, TimestampMixin):
    __tablename__ = "customer_app_attachments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(150))
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerResource(Base, TimestampMixin):
    """Bounded workflow documents, not uploaded bytes or imported ownership."""
    __tablename__ = "customer_app_resources"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("customer_id", "kind", "dedupe_key", name="uq_customer_resource_dedupe"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    garage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("garages.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customer_app_resources.id"), index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class AppointmentSlot(Base):
    __tablename__ = "customer_app_slots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    garage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("garages.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CustomerBookingLink(Base):
    """Explicit ownership bridge for bookings created by the customer app only."""
    __tablename__ = "customer_app_booking_links"
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_accounts.id"), index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_app_vehicles.id"), index=True)
    slot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer_app_slots.id"), nullable=True
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_app_resources.id"), unique=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
