import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(
        self, garage_id: uuid.UUID, start_date: date, end_date: date
    ) -> dict:
        q = select(
            func.count(Job.id).label("total"),
            func.coalesce(
                func.sum(
                    case((Job.status == JobStatus.COMPLETED, Job.final_amount), else_=None)
                ),
                0,
            ).label("revenue"),
            func.sum(case((Job.status == JobStatus.OPEN, 1), else_=0)).label("open"),
            func.sum(case((Job.status == JobStatus.IN_PROGRESS, 1), else_=0)).label("in_progress"),
            func.sum(case((Job.status == JobStatus.WAITING_FOR_PARTS, 1), else_=0)).label("waiting"),
            func.sum(case((Job.status == JobStatus.QUALITY_CHECK, 1), else_=0)).label("quality_check"),
            func.sum(case((Job.status == JobStatus.COMPLETED, 1), else_=0)).label("completed"),
            func.sum(case((Job.status == JobStatus.CANCELLED, 1), else_=0)).label("cancelled"),
        ).where(
            Job.garage_id == garage_id,
            Job.deleted_at.is_(None),
            func.date(Job.created_at) >= start_date,
            func.date(Job.created_at) <= end_date,
        )
        row = (await self.session.execute(q)).one()
        return {
            "total": int(row.total or 0),
            "revenue": Decimal(str(row.revenue or 0)),
            "status_counts": {
                "OPEN": int(row.open or 0),
                "IN_PROGRESS": int(row.in_progress or 0),
                "WAITING_FOR_PARTS": int(row.waiting or 0),
                "QUALITY_CHECK": int(row.quality_check or 0),
                "COMPLETED": int(row.completed or 0),
                "CANCELLED": int(row.cancelled or 0),
            },
        }

    async def get_time_series(
        self,
        garage_id: uuid.UUID,
        start_date: date,
        end_date: date,
        trunc: str,  # 'day', 'week', 'month'
    ) -> list[dict]:
        bucket = func.date_trunc(trunc, Job.created_at)
        q = (
            select(
                bucket.label("bucket"),
                func.count(Job.id).label("job_count"),
                func.sum(case((Job.status == JobStatus.COMPLETED, 1), else_=0)).label("completed"),
                func.coalesce(
                    func.sum(
                        case((Job.status == JobStatus.COMPLETED, Job.final_amount), else_=None)
                    ),
                    0,
                ).label("revenue"),
            )
            .where(
                Job.garage_id == garage_id,
                Job.deleted_at.is_(None),
                func.date(Job.created_at) >= start_date,
                func.date(Job.created_at) <= end_date,
            )
            .group_by(bucket)
            .order_by(bucket.asc())
        )
        rows = (await self.session.execute(q)).all()
        return [
            {
                "bucket": row.bucket,
                "job_count": int(row.job_count),
                "completed_count": int(row.completed),
                "revenue": Decimal(str(row.revenue or 0)),
            }
            for row in rows
        ]
