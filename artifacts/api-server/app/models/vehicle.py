import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin


class Vehicle(Base, SoftDeleteMixin):
    __tablename__ = "vehicles"
    __table_args__ = (
        Index("ix_vehicles_customer_id", "customer_id"),
        Index("ix_vehicles_garage_id", "garage_id"),
        Index("ix_vehicles_registration_plate", "registration_plate"),
        Index("ix_vehicles_deleted_at", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    garage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("garages.id", ondelete="CASCADE"), nullable=False
    )
    make: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    registration_plate: Mapped[str] = mapped_column(String(50), nullable=False)
    vin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    colour: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="vehicles")
    garage: Mapped["Garage"] = relationship("Garage", back_populates="vehicles")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="vehicle")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="vehicle")
