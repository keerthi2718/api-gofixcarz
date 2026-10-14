"""Verified customer identities are distinct from garage contact records."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class CustomerIdentity(Base, TimestampMixin):
    __tablename__ = "customer_identities"
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_accounts.id"), primary_key=True)
    mobile: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terms_version: Mapped[str] = mapped_column(String(50), nullable=False)
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    address: Mapped[dict | None] = mapped_column(JSONB)


class CustomerSession(Base):
    __tablename__ = "customer_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_identities.customer_id"), index=True)
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_name: Mapped[str | None] = mapped_column(String(100))


class CustomerRefreshCredential(Base):
    __tablename__ = "customer_refresh_credentials"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_sessions.id"), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerOTPChallenge(Base):
    __tablename__ = "customer_otp_challenges"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    root_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    identifier: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_identities.customer_id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_sessions.id"))
    pending_registration: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CustomerAuthRateBucket(Base):
    __tablename__ = "customer_auth_rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
