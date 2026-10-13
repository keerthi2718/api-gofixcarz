from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Nonblank = Annotated[str, Field(min_length=1, max_length=500)]
Version = Annotated[int, Field(strict=True, ge=1)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Change(StrictInput):
    reason: Nonblank
    expected_version: Version


class GarageStatus(Change):
    operational_status: Literal["ACTIVE", "SUSPENDED"]


class GarageVerification(Change):
    verification_status: Literal["UNVERIFIED", "VERIFIED", "REJECTED"]


class Assignment(Change):
    assignee_id: UUID | None


class Priority(Change):
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"]


class TicketStatus(StrictInput):
    expected_version: Version
    status: Literal["OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "RESOLVED", "CLOSED"]
    resolution: Nonblank | None = None

    @model_validator(mode="after")
    def resolution_required(self):
        if self.status in ("RESOLVED", "CLOSED") and not self.resolution:
            raise ValueError("Resolution is required")
        return self


class Reply(StrictInput):
    client_message_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=2000)


class Audience(StrictInput):
    recipient_roles: list[Literal["GARAGE_OWNER"]] = Field(min_length=1, max_length=1)
    garage_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    city: str | None = Field(default=None, max_length=100)
    operational_status: Literal["ACTIVE", "SUSPENDED"] | None = None


class AnnouncementPreview(StrictInput):
    audience: Audience
    channels: list[Literal["IN_APP", "PUSH", "SMS", "EMAIL"]] = Field(min_length=1, max_length=4)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Duplicate channels")
        return values


class AnnouncementSend(StrictInput):
    preview_id: UUID
    reason: Nonblank


class ReportFilters(StrictInput):
    date_from: date | None = None
    date_to: date | None = None
    timezone: str = "UTC"
    city: str | None = None
    garage_id: UUID | None = None
    owner_id: UUID | None = None
    service_id: UUID | None = None


class ExportRequest(StrictInput):
    report_type: Literal["OPERATIONS", "FINANCE", "GARAGE_OWNER_PERFORMANCE"]
    format: Literal["CSV", "XLSX"]
    filters: ReportFilters
    snapshot_id: UUID | None = None
    exclude_inactive: bool = False


class CustomerSource(StrictInput):
    id: UUID
    source: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    mobile: str | None = Field(default=None, max_length=30)
    account_status: Literal["ACTIVE", "INACTIVE", "BLOCKED", "DELETED"] = "ACTIVE"
    last_activity_at: datetime | None = None
    garage_ids: list[UUID] = Field(min_length=1, max_length=1000)


class RecordSource(StrictInput):
    id: UUID
    source: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=200)
    kind: Literal["INVOICE", "PAYMENT", "REFUND", "DISPUTE", "REVIEW", "VEHICLE", "TICKET",
                  "DELIVERY", "BOOKING_EVENT"]
    garage_id: UUID
    customer_id: UUID | None = None
    booking_id: UUID | None = None
    job_id: UUID | None = None
    parent_id: UUID | None = None
    status: str = Field(min_length=1, max_length=40)
    occurred_at: datetime
    amount: Annotated[int, Field(strict=True, ge=0, le=10**14)] | None = None
    currency: Literal["INR"] | None = None
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_domain(self):
        allowed_status = {
            "INVOICE": {"DRAFT", "ISSUED", "PAID", "VOID"},
            "PAYMENT": {"CREATED", "PENDING", "CAPTURED", "FAILED"},
            "REFUND": {"PENDING", "SETTLED", "FAILED"},
            "DISPUTE": {"OPEN", "UNDER_REVIEW", "WON", "LOST", "CLOSED"},
            "REVIEW": {"PENDING", "PUBLISHED", "HIDDEN"},
            "VEHICLE": {"ACTIVE", "ARCHIVED"},
            "TICKET": {"OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "RESOLVED", "CLOSED"},
            "DELIVERY": {"QUEUED", "DELIVERED", "FAILED", "SKIPPED"},
            "BOOKING_EVENT": {"ACCEPTED", "REJECTED", "CONVERTED", "CANCELLED", "EXPIRED"},
        }
        allowed_keys = {
            "INVOICE": {"invoice_number", "subtotal", "tax_amount", "discount_amount"},
            "PAYMENT": {"gateway_reference", "failure_code"},
            "REFUND": {"reason"},
            "DISPUTE": {"reason", "evidence_summary"},
            "REVIEW": {"rating", "text"},
            "VEHICLE": {"registration_number", "brand", "model", "fuel_type"},
            "TICKET": {"subject", "description", "priority"},
            "DELIVERY": {"channel", "recipient_role", "failure_code"},
            "BOOKING_EVENT": {"reason", "actor_id"},
        }
        if self.status not in allowed_status[self.kind] or set(self.payload) - allowed_keys[self.kind]:
            raise ValueError("Invalid source status or unsafe payload fields")
        if not self.occurred_at.tzinfo:
            raise ValueError("Source event timestamps require a timezone")
        if self.kind in ("INVOICE", "PAYMENT", "REFUND") and (self.amount is None or not self.currency):
            raise ValueError("Financial sources require integer INR paise")
        if self.kind in ("PAYMENT", "REFUND", "DISPUTE") and not self.parent_id:
            raise ValueError("A parent invoice/payment is required")
        if self.kind in ("REVIEW", "VEHICLE") and not self.customer_id:
            raise ValueError("Customer account is required")
        if self.kind == "BOOKING_EVENT" and not self.booking_id:
            raise ValueError("Booking ID required")
        if self.kind == "BOOKING_EVENT" and self.payload.get("actor_id"):
            UUID(self.payload["actor_id"])
        if self.kind == "REVIEW":
            rating = self.payload.get("rating")
            if type(rating) is not int or not 1 <= rating <= 5:
                raise ValueError("Review rating must be 1..5")
        if self.kind == "TICKET" and (
            not str(self.payload.get("subject", "")).strip() or
            self.payload.get("priority", "NORMAL") not in ("LOW", "NORMAL", "HIGH", "URGENT")
        ):
            raise ValueError("Ticket subject and valid priority required")
        for key, value in self.payload.items():
            if key in ("subtotal", "tax_amount", "discount_amount"):
                if type(value) is not int or value < 0:
                    raise ValueError("Invoice components require nonnegative integer paise")
            elif key != "rating" and (not isinstance(value, str) or len(value) > 2000):
                raise ValueError("Source descriptions must be bounded strings")
        return self


class SourceBatch(StrictInput):
    accounts: list[CustomerSource] = Field(default_factory=list, max_length=1000)
    records: list[RecordSource] = Field(default_factory=list, max_length=10000)
