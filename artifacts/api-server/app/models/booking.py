import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database.base import Base, SoftDeleteMixin


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CONVERTED = "CONVERTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Booking(Base, SoftDeleteMixin):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_garage_id", "garage_id"),
        Index("ix_bookings_customer_id", "customer_id"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_booking_date", "booking_date"),
        Index("ix_bookings_deleted_at", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    garage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("garages.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[BookingStatus] = mapped_column(
        SAEnum(BookingStatus, name="booking_status"), default=BookingStatus.PENDING, nullable=False
    )
    booking_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_mobile: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_requested: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    garage: Mapped["Garage"] = relationship("Garage", back_populates="bookings")
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="bookings")
    vehicle: Mapped[Optional["Vehicle"]] = relationship("Vehicle", back_populates="bookings")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="booking")

    @property
    def scheduled_date(self) -> Optional[date]:
        return self.booking_date
