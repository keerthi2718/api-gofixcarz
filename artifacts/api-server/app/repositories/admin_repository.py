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
from app.core.admin_read_filters import apply_admin_filters


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

    def garages_query(self, search=None, user_id=None, filters=None, location_issue=None):
        query = select(Garage).where(Garage.deleted_at.is_(None))
        if search:
            term = f"%{search}%"
            query = query.where(or_(
                Garage.name.ilike(term), Garage.owner.ilike(term), Garage.city.ilike(term),
            ))
        if user_id is not None:
            query = query.where(Garage.user_id == user_id)
        if location_issue is not None:
            # Explicit NULL arms avoid SQL's unknown result for partial pins.
            issue = or_(
                Garage.latitude.is_(None), Garage.longitude.is_(None),
                ~Garage.latitude.between(-90, 90),
                ~Garage.longitude.between(-180, 180),
            )
            query = query.where(issue if location_issue else ~issue)
        return apply_admin_filters(query, filters).order_by(Garage.created_at.desc(), Garage.id.desc())

    def jobs_query(self, garage_id=None, status=None, search=None, date_from=None, date_to=None,
                   billing_issues=False, filters=None):
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
        return apply_admin_filters(query, filters, Job.created_at).order_by(Job.created_at.desc(), Job.id.desc())

    def bookings_query(self, garage_id=None, status=None, filters=None, customer_id=None, search=None):
        query = select(Booking).join(Garage, Booking.garage_id == Garage.id).where(
            Booking.deleted_at.is_(None), Garage.deleted_at.is_(None),
        )
        if garage_id is not None:
            query = query.where(Booking.garage_id == garage_id)
        if status is not None:
            query = query.where(Booking.status == status)
        if customer_id is not None:
            query = query.where(Booking.customer_id == customer_id)
        if search:
            term = f"%{search}%"
            query = query.where(or_(Booking.customer_name.ilike(term), Booking.customer_mobile.ilike(term),
                                    Booking.service_requested.ilike(term)))
        return apply_admin_filters(query, filters, Booking.created_at).order_by(Booking.created_at.desc(), Booking.id.desc())

    def audit_query(self, actor_id=None, action=None, date_from=None, date_to=None, filters=None):
        query = select(AdminAuditLog)
        if actor_id is not None:
            query = query.where(or_(AdminAuditLog.actor_id == actor_id, AdminAuditLog.admin_account_id == actor_id))
        if action:
            query = query.where(AdminAuditLog.action == action)
        if date_from:
            query = query.where(func.date(AdminAuditLog.created_at) >= date_from)
        if date_to:
            query = query.where(func.date(AdminAuditLog.created_at) <= date_to)
        return apply_admin_filters(query, filters, AdminAuditLog.created_at).order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())

    async def status_counts(self, garage_id=None, start_date=None, end_date=None, filters=None):
        query = select(Job.status, func.count(Job.id)).join(Garage, Job.garage_id == Garage.id).where(
            *job_scope(garage_id),
        )
        if start_date:
            query = query.where(func.date(Job.created_at) >= start_date)
        if end_date:
            query = query.where(func.date(Job.created_at) <= end_date)
        query = apply_admin_filters(query, filters, Job.created_at)
        rows = (await self.session.execute(query.group_by(Job.status))).all()
        counts = {s.value: 0 for s in JobStatus}
        counts.update({status.value: count for status, count in rows})
        return counts

    async def revenue(self, garage_id=None, start_date=None, end_date=None, filters=None):
        query = select(func.coalesce(func.sum(Job.final_amount), 0)).select_from(Job).join(
            Garage, Job.garage_id == Garage.id,
        ).where(
            *job_scope(garage_id), Job.status == JobStatus.COMPLETED,
            Job.completed_at.is_not(None), Job.final_amount.is_not(None),
        )
        if start_date:
            query = query.where(Job.completed_at >= filters.boundary(start_date)) if filters else query.where(func.date(Job.completed_at) >= start_date)
        if end_date:
            query = query.where(Job.completed_at < filters.boundary(end_date, exclusive_end=True)) if filters else query.where(func.date(Job.completed_at) <= end_date)
        return (await self.session.execute(apply_admin_filters(query, filters, Job.completed_at))).scalar_one()

    async def count(self, query):
        return (await self.session.execute(
            select(func.count()).select_from(query.order_by(None).subquery())
        )).scalar_one()

    async def time_series(self, garage_id, start_date: date, end_date: date, trunc: str, filters=None):
        created_bucket = func.date_trunc(trunc, func.timezone(filters.timezone, Job.created_at) if filters else Job.created_at)
        jobs = select(created_bucket.label("bucket"), func.count(Job.id).label("count")).join(
            Garage, Job.garage_id == Garage.id,
        ).where(
            *job_scope(garage_id),
            Job.created_at >= filters.boundary(start_date) if filters else func.date(Job.created_at) >= start_date,
            Job.created_at < filters.boundary(end_date, exclusive_end=True) if filters else func.date(Job.created_at) <= end_date,
        ).group_by(created_bucket)
        completed_bucket = func.date_trunc(trunc, func.timezone(filters.timezone, Job.completed_at) if filters else Job.completed_at)
        revenue = select(
            completed_bucket.label("bucket"),
            func.count(Job.id).label("count"),
            func.coalesce(func.sum(Job.final_amount), 0).label("revenue"),
        ).join(Garage, Job.garage_id == Garage.id).where(
            *job_scope(garage_id), Job.status == JobStatus.COMPLETED,
            Job.completed_at.is_not(None),
            Job.completed_at >= filters.boundary(start_date) if filters else func.date(Job.completed_at) >= start_date,
            Job.completed_at < filters.boundary(end_date, exclusive_end=True) if filters else func.date(Job.completed_at) <= end_date,
        ).group_by(completed_bucket)
        return (
            (await self.session.execute(apply_admin_filters(jobs, filters, Job.created_at))).all(),
            (await self.session.execute(apply_admin_filters(revenue, filters, Job.completed_at))).all(),
        )
