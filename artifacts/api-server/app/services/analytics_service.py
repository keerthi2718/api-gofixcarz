import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import AnalyticsResponse, JobStatusCounts, TimeSeriesPoint


def _date_label(bucket, trunc: str) -> str:
    if bucket is None:
        return ""
    d = bucket.date() if hasattr(bucket, "date") else bucket
    if trunc == "day":
        return d.strftime("%Y-%m-%d")
    if trunc == "week":
        return f"Week {d.strftime('%W')} {d.year}"
    if trunc == "month":
        return d.strftime("%b %Y")
    return str(d)


def _period_dates(period: str, start_date=None, end_date=None):
    today = date.today()
    if period == "daily":
        return today - timedelta(days=6), today, "day"
    if period == "weekly":
        return today - timedelta(weeks=4), today, "week"
    if period == "monthly":
        return today.replace(day=1) - timedelta(days=335), today, "month"
    # custom
    return start_date or today - timedelta(days=29), end_date or today, "day"


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AnalyticsRepository(session)

    async def get(
        self,
        garage_id: uuid.UUID,
        period: str = "monthly",
        start_date=None,
        end_date=None,
    ) -> AnalyticsResponse:
        s, e, trunc = _period_dates(period, start_date, end_date)

        summary = await self.repo.get_summary(garage_id, s, e)
        series = await self.repo.get_time_series(garage_id, s, e, trunc)

        graph = [
            TimeSeriesPoint(
                label=_date_label(row["bucket"], trunc),
                revenue=row["revenue"],
                job_count=row["job_count"],
                completed_count=row["completed_count"],
            )
            for row in series
        ]

        return AnalyticsResponse(
            period=period,
            start_date=s,
            end_date=e,
            total_revenue=summary["revenue"],
            total_jobs=summary["total"],
            status_counts=JobStatusCounts(**summary["status_counts"]),
            graph_data=graph,
        )
