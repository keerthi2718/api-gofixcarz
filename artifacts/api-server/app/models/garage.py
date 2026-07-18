import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin


class Garage(Base, SoftDeleteMixin):
    __tablename__ = "garages"
    __table_args__ = (
        Index("ix_garages_user_id", "user_id"),
        Index("ix_garages_deleted_at", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zipcode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    alternate_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    wheelers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    working_hours: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="garages")
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="garage")
    vehicles: Mapped[list["Vehicle"]] = relationship(
        "Vehicle", back_populates="garage"
    )
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="garage")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="garage")
    service_packages: Mapped[list["ServicePackage"]] = relationship(
        "ServicePackage", back_populates="garage"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="garage"
    )
