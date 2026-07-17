import uuid
from datetime import date, datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.customer import Customer
from app.models.job import Job, JobStatus
from app.models.job_timeline import JobTimeline


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(self, garage_id: uuid.UUID) -> dict:
        today = date.today()
        month_start = today.replace(day=1)

        # Job counts
        job_counts_q = select(
            func.count(Job.id).label("total"),
            func.sum(case((func.date(Job.created_at) == today, 1), else_=0)).label("today"),
            func.sum(case((Job.status == JobStatus.OPEN, 1), else_=0)).label("open"),
            func.sum(case((Job.status == JobStatus.IN_PROGRESS, 1), else_=0)).label("in_progress"),
            func.sum(case((Job.status == JobStatus.COMPLETED, 1), else_=0)).label("completed"),
            func.sum(case((Job.status == JobStatus.CANCELLED, 1), else_=0)).label("cancelled"),
        ).where(Job.garage_id == garage_id, Job.deleted_at.is_(None))
        job_row = (await self.session.execute(job_counts_q)).one()

        # Revenue
        revenue_q = select(
            func.coalesce(
                func.sum(case((func.date(Job.completed_at) == today, Job.final_amount), else_=None)), 0
            ).label("today"),
            func.coalesce(
                func.sum(
                    case(
                        (func.date(Job.completed_at) >= month_start, Job.final_amount),
                        else_=None,
                    )
                ), 0
            ).label("month"),
        ).where(
            Job.garage_id == garage_id,
            Job.status == JobStatus.COMPLETED,
            Job.deleted_at.is_(None),
        )
        rev_row = (await self.session.execute(revenue_q)).one()

        # Booking counts
        booking_q = select(
            func.sum(case((func.date(Booking.created_at) == today, 1), else_=0)).label("today"),
            func.sum(case((Booking.status == BookingStatus.PENDING, 1), else_=0)).label("pending"),
        ).where(Booking.garage_id == garage_id, Booking.deleted_at.is_(None))
        bk_row = (await self.session.execute(booking_q)).one()

        # Recent activities (last 20 timeline events)
        activity_q = (
            select(
                JobTimeline.id,
                JobTimeline.job_id,
                Job.job_number,
                Customer.name.label("customer_name"),
                JobTimeline.status,
                JobTimeline.notes,
                JobTimeline.created_at,
            )
            .join(Job, JobTimeline.job_id == Job.id)
            .join(Customer, Job.customer_id == Customer.id, isouter=True)
            .where(Job.garage_id == garage_id)
            .order_by(JobTimeline.created_at.desc())
            .limit(20)
        )
        activities = (await self.session.execute(activity_q)).all()

        return {
            "jobs_today": int(job_row.today or 0),
            "open_jobs": int(job_row.open or 0),
            "in_progress_jobs": int(job_row.in_progress or 0),
            "completed_jobs": int(job_row.completed or 0),
            "cancelled_jobs": int(job_row.cancelled or 0),
            "bookings_today": int(bk_row.today or 0),
            "pending_bookings": int(bk_row.pending or 0),
            "revenue_today": rev_row.today or 0,
            "revenue_this_month": rev_row.month or 0,
            "recent_activities": [
                {
                    "job_id": str(row.job_id),
                    "job_number": row.job_number,
                    "customer_name": row.customer_name,
                    "status": row.status,
                    "notes": row.notes,
                    "timestamp": row.created_at,
                }
                for row in activities
            ],
        }
