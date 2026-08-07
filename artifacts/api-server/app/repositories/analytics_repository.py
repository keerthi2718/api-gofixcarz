import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(
        self, garage_id: uuid.UUID, start_date: date, end_date: date
    ) -> dict:
        # ── Job counts + status breakdown filtered by created_at ──────────────
        q_jobs = select(
            func.count(Job.id).label("total"),
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

        # ── Revenue filtered by completed_at (money actually earned this period) ─
        q_revenue = select(
            func.coalesce(func.sum(Job.final_amount), 0).label("revenue"),
        ).where(
            Job.garage_id == garage_id,
            Job.deleted_at.is_(None),
            Job.status == JobStatus.COMPLETED,
            Job.completed_at.is_not(None),
            func.date(Job.completed_at) >= start_date,
            func.date(Job.completed_at) <= end_date,
        )

        jobs_row = (await self.session.execute(q_jobs)).one()
        rev_row = (await self.session.execute(q_revenue)).one()

        return {
            "total": int(jobs_row.total or 0),
            "revenue": Decimal(str(rev_row.revenue or 0)),
            "status_counts": {
                "OPEN": int(jobs_row.open or 0),
                "IN_PROGRESS": int(jobs_row.in_progress or 0),
                "WAITING_FOR_PARTS": int(jobs_row.waiting or 0),
                "QUALITY_CHECK": int(jobs_row.quality_check or 0),
                "COMPLETED": int(jobs_row.completed or 0),
                "CANCELLED": int(jobs_row.cancelled or 0),
            },
        }

    async def get_time_series(
        self,
        garage_id: uuid.UUID,
        start_date: date,
        end_date: date,
        trunc: str,  # 'day', 'week', 'month'
    ) -> list[dict]:
        # ── Query 1: job_count per bucket (bucketed by created_at) ────────────
        bucket_created = func.date_trunc(trunc, Job.created_at)
        q_jobs = (
            select(
                bucket_created.label("bucket"),
                func.count(Job.id).label("job_count"),
            )
            .where(
                Job.garage_id == garage_id,
                Job.deleted_at.is_(None),
                func.date(Job.created_at) >= start_date,
                func.date(Job.created_at) <= end_date,
            )
            .group_by(bucket_created)
            .order_by(bucket_created.asc())
        )

        # ── Query 2: revenue + completed_count (bucketed by completed_at) ─────
        bucket_completed = func.date_trunc(trunc, Job.completed_at)
        q_revenue = (
            select(
                bucket_completed.label("bucket"),
                func.count(Job.id).label("completed_count"),
                func.coalesce(func.sum(Job.final_amount), 0).label("revenue"),
            )
            .where(
                Job.garage_id == garage_id,
                Job.deleted_at.is_(None),
                Job.status == JobStatus.COMPLETED,
                Job.completed_at.is_not(None),
                func.date(Job.completed_at) >= start_date,
                func.date(Job.completed_at) <= end_date,
            )
            .group_by(bucket_completed)
            .order_by(bucket_completed.asc())
        )

        jobs_rows = (await self.session.execute(q_jobs)).all()
        rev_rows = (await self.session.execute(q_revenue)).all()

        # ── Merge both result sets by bucket datetime ─────────────────────────
        merged: dict = {}
        for row in jobs_rows:
            merged[row.bucket] = {
                "bucket": row.bucket,
                "job_count": int(row.job_count),
                "completed_count": 0,
                "revenue": Decimal(0),
            }
        for row in rev_rows:
            if row.bucket in merged:
                merged[row.bucket]["completed_count"] = int(row.completed_count)
                merged[row.bucket]["revenue"] = Decimal(str(row.revenue or 0))
            else:
                merged[row.bucket] = {
                    "bucket": row.bucket,
                    "job_count": 0,
                    "completed_count": int(row.completed_count),
                    "revenue": Decimal(str(row.revenue or 0)),
                }

        return [merged[k] for k in sorted(merged.keys())]
