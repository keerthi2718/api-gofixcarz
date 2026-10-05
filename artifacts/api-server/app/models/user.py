import uuid
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin


class UserRole(str, enum.Enum):
    GARAGE_OWNER = "garage_owner"
    ADMIN = "admin"


class User(Base, SoftDeleteMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('garage_owner', 'admin')", name="ck_users_role"),
        Index("ix_users_mobile", "mobile"),
        Index("ix_users_email", "email"),
        Index("ix_users_deleted_at", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Stored as plain 10-digit number; country_code is kept separately.
    mobile: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="91"
    )
    country_code_2: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    terms_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    otp: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    otp_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), default=UserRole.GARAGE_OWNER.value,
        server_default=UserRole.GARAGE_OWNER.value, nullable=False,
    )

    # Relationships
    garages: Mapped[list["Garage"]] = relationship("Garage", back_populates="user")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="user")
