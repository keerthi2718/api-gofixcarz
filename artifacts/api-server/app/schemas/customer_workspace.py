"""Strict customer/participant write contracts and explicit published projections."""
import re
from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, field_validator, model_validator
from app.schemas.customer_app import StrictInput
from app.core.customer_security import now

Fuel = Literal["PETROL", "DIESEL", "CNG", "LPG", "ELECTRIC", "HYBRID"]
Category = Literal["BOOKINGS", "JOBS", "INVOICES", "MESSAGES", "PAYMENTS", "REVIEWS", "SUPPORT"]


class VehicleCreate(StrictInput):
    registration_number: str = Field(min_length=4, max_length=20)
    brand: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    fuel_type: Fuel
    year: int | None = Field(default=None, ge=1950)
    odometer_km: int | None = Field(default=None, ge=0, le=10000000)
    is_default: bool = False

    @field_validator("registration_number")
    @classmethod
    def registration(cls, value):
        value = re.sub(r"[\s-]", "", value).upper()
        if not re.fullmatch(r"[A-Z0-9]{4,20}", value):
            raise ValueError("Registration must contain 4–20 letters/digits")
        return value

    @field_validator("year")
    @classmethod
    def plausible_year(cls, value):
        if value is not None and value > now().year + 1:
            raise ValueError("Year cannot be later than next year")
        return value


class VehiclePatch(StrictInput):
    registration_number: str | None = Field(default=None, min_length=4, max_length=20)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    fuel_type: Fuel | None = None
    year: int | None = Field(default=None, ge=1950)
    odometer_km: int | None = Field(default=None, ge=0, le=10000000)
    _registration = field_validator("registration_number")(VehicleCreate.registration.__func__)
    _year = field_validator("year")(VehicleCreate.plausible_year.__func__)

    @model_validator(mode="after")
    def meaningful(self):
        if not self.model_fields_set:
            raise ValueError("At least one editable field is required")
        for name in ("registration_number", "brand", "model", "fuel_type"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(name + " cannot be null")
        return self


class PhotoSet(StrictInput):
    attachment_id: UUID


class QuoteRequest(StrictInput):
    garage_id: UUID
    vehicle_id: UUID
    service_ids: list[UUID] = Field(min_length=1, max_length=20)
    slot_id: UUID
    notes: str | None = Field(default=None, max_length=2000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.service_ids)) != len(self.service_ids) or len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("IDs must be unique")
        return self


class BookingSubmit(StrictInput):
    quote_id: UUID


class CancelRequest(StrictInput):
    reason: str = Field(min_length=1, max_length=500)


class SlotCreate(StrictInput):
    starts_at: datetime
    ends_at: datetime
    timezone: str = "Asia/Kolkata"
    capacity: int = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown IANA timezone")
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo:
            raise ValueError("Slot timestamps require timezone offsets")
        if self.starts_at <= now() or self.ends_at <= self.starts_at:
            raise ValueError("Slot must have a future start and later end")
        return self


class DeviceRequest(StrictInput):
    platform: Literal["ANDROID", "IOS"]
    push_token: str = Field(min_length=1, max_length=4096)


class NotificationRead(StrictInput):
    is_read: Literal[True]


class ReadAll(StrictInput):
    category: Category | None = None


class ConversationStart(StrictInput):
    booking_id: UUID | None = None
    job_id: UUID | None = None

    @model_validator(mode="after")
    def one_context(self):
        if bool(self.booking_id) == bool(self.job_id):
            raise ValueError("Exactly one booking_id or job_id is required")
        return self


class MessageSend(StrictInput):
    client_message_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=2000)


class ReadMarker(StrictInput):
    last_read_message_id: UUID


class ReviewCreate(StrictInput):
    rating: int = Field(strict=True, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewPatch(StrictInput):
    rating: int | None = Field(default=None, strict=True, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def meaningful(self):
        if not self.model_fields_set or ("rating" in self.model_fields_set and self.rating is None):
            raise ValueError("At least one field required; rating cannot be null")
        return self


class TicketCreate(StrictInput):
    category: Literal["GENERAL", "BOOKING", "SERVICE", "PAYMENT", "ACCOUNT", "TECHNICAL"]
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    booking_id: UUID | None = None
    job_id: UUID | None = None
    invoice_id: UUID | None = None
    payment_id: UUID | None = None
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)


class TicketReply(MessageSend):
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)


class PublishedJob(StrictInput):
    """Only this whitelisted projection, never the garage's raw JSON blobs."""
    findings: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    services: list[str] = Field(default_factory=list, max_length=50)
    parts: list[str] = Field(default_factory=list, max_length=50)
    labour: list[str] = Field(default_factory=list, max_length=50)
    photo_keys: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("findings", "services", "parts", "labour")
    @classmethod
    def bounded(cls, values):
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("Entries must contain 1–500 characters")
        return values


class InvoicePublish(StrictInput):
    invoice_number: str = Field(min_length=1, max_length=100)
    subtotal: int = Field(strict=True, ge=0, le=10**12)
    tax_amount: int = Field(strict=True, ge=0, le=10**12)
    discount_amount: int = Field(default=0, strict=True, ge=0, le=10**12)

    @model_validator(mode="after")
    def total(self):
        if self.discount_amount > self.subtotal + self.tax_amount:
            raise ValueError("Discount cannot exceed subtotal plus tax")
        return self


class Moderation(StrictInput):
    status: Literal["PUBLISHED", "HIDDEN"]


class TicketStatusPatch(StrictInput):
    status: Literal["OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "RESOLVED", "CLOSED"]
