import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database.base import Base, SoftDeleteMixin


class JobStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_PARTS = "WAITING_FOR_PARTS"
    QUALITY_CHECK = "QUALITY_CHECK"
    READY = "READY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Job(Base, SoftDeleteMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("garage_id", "job_number", name="uq_jobs_garage_job_number"),
        Index("ix_jobs_garage_id", "garage_id"),
        Index("ix_jobs_customer_id", "customer_id"),
        Index("ix_jobs_vehicle_id", "vehicle_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_job_number", "job_number"),
        Index("ix_jobs_deleted_at", "deleted_at"),
        Index("ix_jobs_created_at", "created_at"),
        Index("ix_jobs_registration_number", "registration_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_number: Mapped[str] = mapped_column(String(50), nullable=False)
    garage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("garages.id", ondelete="CASCADE"), nullable=False
    )

    # FK references — nullable because jobs can be created from inline details
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    booking_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )

    # Inline customer / vehicle details (populated when no FK records exist)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    registration_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fuel_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    odometer_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # JSONB data blobs
    photos: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    inspection: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    services: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    labour: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    billing: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Status and amounts
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"), default=JobStatus.OPEN, nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    final_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    garage: Mapped["Garage"] = relationship("Garage", back_populates="jobs")
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="jobs")
    vehicle: Mapped[Optional["Vehicle"]] = relationship("Vehicle", back_populates="jobs")
    booking: Mapped[Optional["Booking"]] = relationship("Booking", back_populates="jobs")
    timelines: Mapped[list["JobTimeline"]] = relationship(
        "JobTimeline", back_populates="job", order_by="JobTimeline.created_at.asc()"
    )
