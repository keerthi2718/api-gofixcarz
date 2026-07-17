from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class TimeSeriesPoint(BaseModel):
    label: str          # e.g. "2026-07-01" or "Week 27" or "Jul 2026"
    revenue: Decimal
    job_count: int
    completed_count: int


class JobStatusCounts(BaseModel):
    OPEN: int = 0
    IN_PROGRESS: int = 0
    WAITING_FOR_PARTS: int = 0
    QUALITY_CHECK: int = 0
    COMPLETED: int = 0
    CANCELLED: int = 0


class AnalyticsResponse(BaseModel):
    period: str
    start_date: date
    end_date: date
    total_revenue: Decimal
    total_jobs: int
    status_counts: JobStatusCounts
    graph_data: list[TimeSeriesPoint]
