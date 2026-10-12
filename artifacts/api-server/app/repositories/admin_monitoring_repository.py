"""Read models for persisted owner, booking, job and audit data only."""
from sqlalchemy import String, cast, func, literal, select, union_all
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import selectinload

from app.core.admin_read_filters import apply_admin_filters
from app.models.admin_audit_log import AdminAuditLog
from app.models.booking import Booking, BookingStatus
from app.models.garage import Garage
from app.models.job import Job, JobStatus
from app.models.job_timeline import JobTimeline
from app.models.user import AccountStatus, User, UserRole
from app.repositories.admin_repository import AdminRepository, job_scope


class AdminMonitoringRepository(AdminRepository):
    def owners_query(self, filters, search=None, status=None, include_deleted=False):
        query = self.users_query(search=search, role=UserRole.GARAGE_OWNER.value,
                                 include_deleted=include_deleted or status == AccountStatus.DELETED)
        if status == AccountStatus.DELETED:
            query = query.where(User.deleted_at.is_not(None))
        elif status is not None:
            query = query.where(User.deleted_at.is_(None), User.is_active == (status == AccountStatus.ACTIVE))
        garages = apply_admin_filters(
            select(Garage.user_id).where(Garage.deleted_at.is_(None)), filters,
        )
        # Keep owners with zero garages unless a geography/garage filter was requested.
        if filters.city is not None or filters.garage_id is not None:
            query = query.where(User.id.in_(garages))
        return query

    async def owner_aggregates(self, owners, filters):
        ids = [owner.id for owner in owners]
        if not ids:
            return {}, {}, {}, {}
        garages_query = apply_admin_filters(
            select(Garage).where(Garage.user_id.in_(ids), Garage.deleted_at.is_(None)), filters,
        )
        garages = (await self.session.execute(garages_query)).scalars().all()
        grouped = {}
        for garage in garages:
            grouped.setdefault(garage.user_id, []).append(garage)
        bookings = apply_admin_filters(
            select(Garage.user_id, func.count(Booking.id)).join(Booking, Booking.garage_id == Garage.id)
            .where(Garage.user_id.in_(ids), Garage.deleted_at.is_(None), Booking.deleted_at.is_(None)),
            filters, Booking.created_at,
        ).group_by(Garage.user_id)
        jobs = apply_admin_filters(
            select(Garage.user_id, func.count(Job.id),
                   func.count(Job.id).filter(Job.status == JobStatus.COMPLETED))
            .join(Job, Job.garage_id == Garage.id).where(Garage.user_id.in_(ids), *job_scope()),
            filters, Job.created_at,
        ).group_by(Garage.user_id)
        amounts = apply_admin_filters(
            select(Garage.user_id, func.sum(Job.final_amount)).join(Job, Job.garage_id == Garage.id)
            .where(Garage.user_id.in_(ids), *job_scope(), Job.status == JobStatus.COMPLETED,
                   Job.completed_at.is_not(None), Job.final_amount.is_not(None)),
            filters, Job.completed_at,
        ).group_by(Garage.user_id)
        return (
            grouped, dict((await self.session.execute(bookings)).all()),
            {row[0]: (row[1], row[2]) for row in (await self.session.execute(jobs)).all()},
            dict((await self.session.execute(amounts)).all()),
        )

    async def get_booking(self, booking_id):
        return (await self.session.execute(
            self.bookings_query().where(Booking.id == booking_id)
            .options(selectinload(Booking.customer), selectinload(Booking.vehicle))
        )).scalar_one_or_none()

    async def booking_jobs(self, booking_id):
        return (await self.session.execute(
            self.jobs_query().where(Job.booking_id == booking_id).limit(101)
        )).scalars().all()

    def timeline_query(self, job_id):
        return select(JobTimeline).join(Job).join(Garage).where(
            JobTimeline.job_id == job_id, *job_scope(),
        ).order_by(JobTimeline.created_at.asc(), JobTimeline.id.asc())

    async def booking_exceptions(self, filters):
        query = apply_admin_filters(
            select(Garage.user_id, Garage.city, func.count(Booking.id))
            .join(Booking, Booking.garage_id == Garage.id)
            .where(Garage.deleted_at.is_(None), Booking.deleted_at.is_(None),
                   Booking.status == BookingStatus.REJECTED),
            filters, Booking.created_at,
        ).group_by(Garage.user_id, Garage.city).order_by(Garage.user_id, Garage.city)
        return (await self.session.execute(query)).all()

    async def get_audit(self, audit_id):
        return await self.session.get(AdminAuditLog, audit_id)

    def activity_query(self, filters, customer_id=None, booking_id=None, job_id=None, event_type=None):
        null_uuid = cast(literal(None), UUID(as_uuid=True))

        def event(query, model, timestamp, kind, row_id, status):
            return apply_admin_filters(query.with_only_columns(
                (literal(kind + ":") + cast(row_id, String)).label("id"),
                literal(kind).label("event_type"), model.customer_id,
                Garage.user_id.label("owner_id"), Garage.id.label("garage_id"),
                (model.id if model is Booking else model.booking_id).label("booking_id"),
                (null_uuid if model is Booking else model.id).label("job_id"),
                timestamp.label("timestamp"), cast(status, String).label("status"),
                literal("booking" if model is Booking else
                        "job_timeline" if kind == "JOB_STATUS_RECORDED" else "job").label("source"),
            ), filters, timestamp)

        booking_base = select(Booking).join(Garage).where(
            Booking.deleted_at.is_(None), Garage.deleted_at.is_(None),
        )
        job_base = select(Job).join(Garage).where(*job_scope())
        events = [
            # Creation records do not preserve the original booking/job state.
            event(booking_base, Booking, Booking.created_at, "BOOKING_CREATED", Booking.id, literal(None)),
            event(job_base, Job, Job.created_at, "JOB_CREATED", Job.id, literal(None)),
            event(job_base.where(Job.completed_at.is_not(None), Job.status == JobStatus.COMPLETED),
                  Job, Job.completed_at, "JOB_COMPLETED", Job.id, literal("COMPLETED")),
            event(job_base.join(JobTimeline, JobTimeline.job_id == Job.id), Job,
                  JobTimeline.created_at, "JOB_STATUS_RECORDED", JobTimeline.id, JobTimeline.status),
        ]
        combined = union_all(*events).subquery()
        query = select(combined)
        for column, value in [(combined.c.customer_id, customer_id), (combined.c.booking_id, booking_id),
                              (combined.c.job_id, job_id), (combined.c.event_type, event_type)]:
            if value is not None:
                query = query.where(column == value)
        return query.order_by(combined.c.timestamp.desc(), combined.c.id.desc())

    async def activity_page(self, query, page, page_size):
        total = (await self.session.execute(
            select(func.count()).select_from(query.order_by(None).subquery())
        )).scalar_one()
        items = (await self.session.execute(
            query.offset((page - 1) * page_size).limit(page_size)
        )).mappings().all()
        return items, total
