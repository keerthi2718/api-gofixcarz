import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool

from app.core.money import Money
from app.schemas.auth import UserResponse
from app.schemas.garage import GarageResponse


class AdminUserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: StrictBool


class AdminUserDetail(UserResponse):
    garages: list[GarageResponse]


class AdminGarageDetail(GarageResponse):
    total_jobs: int
    completed_jobs: int
    total_revenue: Money
    billing_issue_count: int


class AdminDashboardResponse(BaseModel):
    total_users: int
    active_users: int
    total_garages: int
    total_jobs: int
    jobs_today: int
    status_counts: dict[str, int]
    total_bookings: int
    pending_bookings: int
    revenue_today: Money
    revenue_this_month: Money
    total_revenue: Money
    billing_issue_count: int
    filters: dict | None = None
    generated_at: datetime | None = None
    metric_bases: dict[str, str] | None = None


class AdminTimeSeriesPoint(BaseModel):
    label: str
    job_count: int
    completed_count: int
    revenue: Money


class AdminAnalyticsResponse(BaseModel):
    garage_id: uuid.UUID | None
    period: Literal["daily", "weekly", "monthly", "custom"]
    start_date: date
    end_date: date
    total_jobs: int
    total_revenue: Money
    status_counts: dict[str, int]
    graph_data: list[AdminTimeSeriesPoint]
    filters: dict | None = None
    generated_at: datetime | None = None
    metric_bases: dict[str, str] | None = None


class AdminAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_id: uuid.UUID | None
    admin_account_id: uuid.UUID | None = None
    action: str
    resource_id: uuid.UUID | None
    details: dict
    created_at: datetime
