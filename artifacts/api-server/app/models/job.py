import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database.base import Base, SoftDeleteMixin


class JobStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_PARTS = "WAITING_FOR_PARTS"
    QUALITY_CHECK = "QUALITY_CHECK"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Job(Base, SoftDeleteMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_garage_id", "garage_id"),
        Index("ix_jobs_customer_id", "customer_id"),
        Index("ix_jobs_vehicle_id", "vehicle_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_job_number", "job_number"),
        Index("ix_jobs_deleted_at", "deleted_at"),
        Index("ix_jobs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    garage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("garages.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    booking_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
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
    customer: Mapped["Customer"] = relationship("Customer", back_populates="jobs")
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="jobs")
    booking: Mapped[Optional["Booking"]] = relationship("Booking", back_populates="jobs")
    timelines: Mapped[list["JobTimeline"]] = relationship(
        "JobTimeline", back_populates="job", order_by="JobTimeline.created_at.desc()"
    )
