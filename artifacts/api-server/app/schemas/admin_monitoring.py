from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auth import UserResponse
from app.schemas.booking import BookingDetailResponse
from app.schemas.garage import GarageResponse
from app.schemas.response import PaginatedData


class AdminOwnerSummary(UserResponse):
    display_name: str | None
    garage_ids: list[UUID]
    total_garages: int
    related_garages_truncated: bool
    cities: list[str]
    bookings: int
    jobs_created: int
    completed_jobs: int
    completed_job_amount_paise: int
    currency: Literal["INR"] = "INR"
    # There is no review or payment source in this phase.
    average_rating: float | None = None


class AdminOwnerDetail(AdminOwnerSummary):
    garages: list[GarageResponse]


class AdminBookingDetail(BookingDetailResponse):
    linked_job_ids: list[UUID]
    linked_jobs_truncated: bool
    decision_actor: UUID | None = None
    decision_reason: str | None = None
    decision_timestamp: datetime | None = None
    missing_history: list[str]
    history: list[dict] = []
    history_truncated: bool = False


class AdminTimelineEvent(BaseModel):
    id: UUID
    job_id: UUID
    status: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminActivityEvent(BaseModel):
    id: str
    event_type: str
    customer_id: UUID | None
    owner_id: UUID
    garage_id: UUID
    booking_id: UUID | None
    job_id: UUID | None
    timestamp: datetime
    status: str | None
    source: str


class AdminReportMetadata(BaseModel):
    filters: dict
    generated_at: datetime
    metric_bases: dict[str, str]
    unavailable_data_sources: list[str]


class AdminOwnerPage(PaginatedData[AdminOwnerSummary], AdminReportMetadata):
    pass


class AdminOwnerDetailResponse(AdminOwnerDetail, AdminReportMetadata):
    pass


class AdminActivityPage(PaginatedData[AdminActivityEvent]):
    filters: dict
    generated_at: datetime
    unavailable_history: list[str]
    restricted_history: list[str] = []


class AdminFunnelResponse(BaseModel):
    booking_id: UUID
    customer_id: UUID | None
    garage_id: UUID
    job_ids: list[UUID]
    linked_jobs_truncated: bool
    events: PaginatedData[AdminActivityEvent]
    data_coverage: dict[str, bool]


class AdminBookingExceptionGroup(BaseModel):
    owner_id: UUID
    city: str | None
    reason: str
    count: int


class AdminBookingExceptionsResponse(BaseModel):
    filters: dict
    generated_at: datetime
    cohort: str
    rejected: int
    reason_counts: dict[str, int]
    breakdown: list[AdminBookingExceptionGroup]
    breakdown_truncated: bool
    unavailable_states: list[str]
    reason_history_available: bool
