import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.job import Job, JobStatus
from app.models.job_timeline import JobTimeline
from app.schemas.job import JobCreate, JobUpdate


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _generate_job_number(self) -> str:
        """Generate a unique job number of the form JOB-YYYYMMDD-NNNN."""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"JOB-{today}-"
        # Count jobs created today to produce a sequence number
        count_q = select(func.count()).where(Job.job_number.like(f"{prefix}%"))
        count: int = (await self.session.execute(count_q)).scalar_one()
        return f"{prefix}{count + 1:04d}"

    async def _add_timeline(
        self, job_id: uuid.UUID, status: JobStatus, notes: Optional[str] = None
    ) -> JobTimeline:
        entry = JobTimeline(
            id=uuid.uuid4(),
            job_id=job_id,
            status=status.value,
            notes=notes,
        )
        self.session.add(entry)
        return entry

    # ── Queries ───────────────────────────────────────────────────────────────

    async def get_by_id(
        self, job_id: uuid.UUID, garage_id: uuid.UUID, load_relations: bool = False
    ) -> Optional[Job]:
        q = select(Job).where(
            Job.id == job_id,
            Job.garage_id == garage_id,
            Job.deleted_at.is_(None),
        )
        if load_relations:
            q = q.options(
                selectinload(Job.customer),
                selectinload(Job.vehicle),
                selectinload(Job.timelines),
            )
        result = await self.session.execute(q)
        return result.scalar_one_or_none()

    async def list(
        self,
        garage_id: uuid.UUID,
        search: Optional[str] = None,
        status: Optional[JobStatus] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Job], int]:
        from app.models.customer import Customer
        from app.models.vehicle import Vehicle

        base_q = (
            select(Job)
            .join(Customer, Job.customer_id == Customer.id, isouter=True)
            .join(Vehicle, Job.vehicle_id == Vehicle.id, isouter=True)
            .where(Job.garage_id == garage_id, Job.deleted_at.is_(None))
        )

        if search:
            term = f"%{search}%"
            base_q = base_q.where(
                or_(
                    Job.job_number.ilike(term),
                    Customer.name.ilike(term),
                    Vehicle.registration_plate.ilike(term),
                )
            )
        if status:
            base_q = base_q.where(Job.status == status)
        if date_from:
            base_q = base_q.where(func.date(Job.created_at) >= date_from)
        if date_to:
            base_q = base_q.where(func.date(Job.created_at) <= date_to)

        # Sorting
        sort_col = getattr(Job, sort_by, Job.created_at)
        order = sort_col.desc() if sort_dir.lower() == "desc" else sort_col.asc()
        base_q = base_q.order_by(order)

        count_q = select(func.count()).select_from(
            base_q.with_only_columns(Job.id).subquery()
        )
        total: int = (await self.session.execute(count_q)).scalar_one()

        items_q = (
            base_q
            .options(selectinload(Job.customer), selectinload(Job.vehicle))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(items_q)).scalars().all()
        return list(rows), total

    # ── Mutations ─────────────────────────────────────────────────────────────

    async def create(self, garage_id: uuid.UUID, data: JobCreate) -> Job:
        job_number = await self._generate_job_number()
        job = Job(
            id=uuid.uuid4(),
            garage_id=garage_id,
            job_number=job_number,
            status=JobStatus.OPEN,
            **data.model_dump(),
        )
        self.session.add(job)
        await self.session.flush()
        await self._add_timeline(job.id, JobStatus.OPEN, "Job created")
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def update(self, job: Job, data: JobUpdate) -> Job:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(job, field, value)
        job.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def change_status(
        self, job: Job, new_status: JobStatus, notes: Optional[str] = None
    ) -> Job:
        job.status = new_status
        job.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self._add_timeline(job.id, new_status, notes)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def complete(self, job: Job, final_amount=None, notes: Optional[str] = None) -> Job:
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = job.completed_at
        if final_amount is not None:
            job.final_amount = final_amount
        await self.session.flush()
        await self._add_timeline(job.id, JobStatus.COMPLETED, notes or "Job completed")
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def delete(self, job: Job) -> None:
        job.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
