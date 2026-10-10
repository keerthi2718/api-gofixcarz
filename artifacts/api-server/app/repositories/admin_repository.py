import uuid
from datetime import date

from sqlalchemy import JSON, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.admin_audit_log import AdminAuditLog
from app.models.booking import Booking
from app.models.garage import Garage
from app.models.job import Job, JobStatus
from app.models.user import User


def billing_issue_condition():
    return (
        (Job.status == JobStatus.COMPLETED)
        & or_(
            Job.final_amount.is_(None), Job.billing.is_(None),
            Job.billing == JSON.NULL, Job.completed_at.is_(None),
        )
    )


def job_scope(garage_id: uuid.UUID | None = None):
    conditions = [Job.deleted_at.is_(None), Garage.deleted_at.is_(None)]
    if garage_id is not None:
        conditions.append(Job.garage_id == garage_id)
    return conditions


class AdminRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def page(self, query, page: int, page_size: int):
        count = select(func.count()).select_from(query.order_by(None).subquery())
        total = (await self.session.execute(count)).scalar_one()
        rows = (await self.session.execute(
            query.offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return rows, total

    async def get_user(self, user_id, include_deleted=False):
        query = select(User).where(User.id == user_id)
        if not include_deleted:
            query = query.where(User.deleted_at.is_(None))
        return (await self.session.execute(
            query
        )).scalar_one_or_none()

    async def get_garage(self, garage_id):
        return (await self.session.execute(
            select(Garage).where(Garage.id == garage_id, Garage.deleted_at.is_(None))
        )).scalar_one_or_none()

    async def get_job(self, job_id):
        return (await self.session.execute(
            select(Job).join(Garage, Job.garage_id == Garage.id)
            .where(Job.id == job_id, *job_scope())
            .options(selectinload(Job.customer), selectinload(Job.vehicle), selectinload(Job.timelines))
        )).scalar_one_or_none()

    def users_query(self, search=None, is_active=None, role=None, include_deleted=False):
        query = select(User)
        if not include_deleted:
            query = query.where(User.deleted_at.is_(None))
        if search:
            term = f"%{search}%"
            query = query.where(or_(User.name.ilike(term), User.email.ilike(term), User.mobile.ilike(term)))
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if role is not None:
            query = query.where(User.role == role)
        return query.order_by(User.created_at.desc(), User.id.desc())

    def garages_query(self, search=None, user_id=None):
        query = select(Garage).where(Garage.deleted_at.is_(None))
        if search:
            term = f"%{search}%"
            query = query.where(or_(
                Garage.name.ilike(term), Garage.owner.ilike(term), Garage.city.ilike(term),
            ))
        if user_id is not None:
            query = query.where(Garage.user_id == user_id)
        return query.order_by(Garage.created_at.desc(), Garage.id.desc())

    def jobs_query(self, garage_id=None, status=None, search=None, date_from=None, date_to=None,
                   billing_issues=False):
        query = select(Job).join(Garage, Job.garage_id == Garage.id).where(*job_scope(garage_id))
        if status is not None:
            query = query.where(Job.status == status)
        if search:
            term = f"%{search}%"
            query = query.where(or_(
                Job.job_number.ilike(term), Job.customer_name.ilike(term),
                Job.registration_number.ilike(term),
            ))
        if date_from:
            query = query.where(func.date(Job.created_at) >= date_from)
        if date_to:
            query = query.where(func.date(Job.created_at) <= date_to)
        if billing_issues:
            query = query.where(billing_issue_condition())
        return query.order_by(Job.created_at.desc(), Job.id.desc())

    def bookings_query(self, garage_id=None, status=None):
        query = select(Booking).join(Garage, Booking.garage_id == Garage.id).where(
            Booking.deleted_at.is_(None), Garage.deleted_at.is_(None),
        )
        if garage_id is not None:
            query = query.where(Booking.garage_id == garage_id)
        if status is not None:
            query = query.where(Booking.status == status)
        return query.order_by(Booking.created_at.desc(), Booking.id.desc())

    def audit_query(self, actor_id=None, action=None, date_from=None, date_to=None):
        query = select(AdminAuditLog)
        if actor_id is not None:
            query = query.where(or_(AdminAuditLog.actor_id == actor_id, AdminAuditLog.admin_account_id == actor_id))
        if action:
            query = query.where(AdminAuditLog.action == action)
        if date_from:
            query = query.where(func.date(AdminAuditLog.created_at) >= date_from)
        if date_to:
            query = query.where(func.date(AdminAuditLog.created_at) <= date_to)
        return query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())

    async def status_counts(self, garage_id=None, start_date=None, end_date=None):
        query = select(Job.status, func.count(Job.id)).join(Garage, Job.garage_id == Garage.id).where(
            *job_scope(garage_id),
        )
        if start_date:
            query = query.where(func.date(Job.created_at) >= start_date)
        if end_date:
            query = query.where(func.date(Job.created_at) <= end_date)
        rows = (await self.session.execute(query.group_by(Job.status))).all()
        counts = {s.value: 0 for s in JobStatus}
        counts.update({status.value: count for status, count in rows})
        return counts

    async def revenue(self, garage_id=None, start_date=None, end_date=None):
        query = select(func.coalesce(func.sum(Job.final_amount), 0)).select_from(Job).join(
            Garage, Job.garage_id == Garage.id,
        ).where(
            *job_scope(garage_id), Job.status == JobStatus.COMPLETED,
            Job.completed_at.is_not(None), Job.final_amount.is_not(None),
        )
        if start_date:
            query = query.where(func.date(Job.completed_at) >= start_date)
        if end_date:
            query = query.where(func.date(Job.completed_at) <= end_date)
        return (await self.session.execute(query)).scalar_one()

    async def count(self, query):
        return (await self.session.execute(
            select(func.count()).select_from(query.order_by(None).subquery())
        )).scalar_one()

    async def time_series(self, garage_id, start_date: date, end_date: date, trunc: str):
        created_bucket = func.date_trunc(trunc, Job.created_at)
        jobs = select(created_bucket.label("bucket"), func.count(Job.id).label("count")).join(
            Garage, Job.garage_id == Garage.id,
        ).where(
            *job_scope(garage_id),
            func.date(Job.created_at) >= start_date, func.date(Job.created_at) <= end_date,
        ).group_by(created_bucket)
        completed_bucket = func.date_trunc(trunc, Job.completed_at)
        revenue = select(
            completed_bucket.label("bucket"),
            func.count(Job.id).label("count"),
            func.coalesce(func.sum(Job.final_amount), 0).label("revenue"),
        ).join(Garage, Job.garage_id == Garage.id).where(
            *job_scope(garage_id), Job.status == JobStatus.COMPLETED,
            Job.completed_at.is_not(None),
            func.date(Job.completed_at) >= start_date, func.date(Job.completed_at) <= end_date,
        ).group_by(completed_bucket)
        return (
            (await self.session.execute(jobs)).all(),
            (await self.session.execute(revenue)).all(),
        )
