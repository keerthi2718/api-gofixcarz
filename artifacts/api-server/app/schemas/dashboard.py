from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class RecentActivity(BaseModel):
    job_id: str
    job_number: str
    customer_name: Optional[str]
    status: str
    notes: Optional[str]
    timestamp: datetime

    model_config = {"from_attributes": True}


class DashboardResponse(BaseModel):
    jobs_today: int
    open_jobs: int
    in_progress_jobs: int
    completed_jobs: int
    cancelled_jobs: int
    bookings_today: int
    pending_bookings: int
    revenue_today: Decimal
    revenue_this_month: Decimal
    recent_activities: list[RecentActivity]
