import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.job import Job, JobStatus
from app.models.job_timeline import JobTimeline
from app.schemas.job import JobCreate, JobUpdate


# GST rate applied at billing completion
_GST_RATE = Decimal("0.18")


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _next_job_seq(self, garage_id: uuid.UUID) -> int:
        """Atomically increment and return the next job sequence number for a garage.

        Uses UPDATE … RETURNING which is a single atomic statement in PostgreSQL.
        """
        from app.models.garage import Garage
        stmt = (
            update(Garage)
            .where(Garage.id == garage_id)
            .values(job_seq=Garage.job_seq + 1)
            .returning(Garage.job_seq)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

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
                    Job.customer_name.ilike(term),
                    Job.registration_number.ilike(term),
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
        seq = await self._next_job_seq(garage_id)
        job_number = f"JC-{seq:03d}"

        # Build the job from the schema — only pass known model fields
        job = Job(
            id=uuid.uuid4(),
            garage_id=garage_id,
            job_number=job_number,
            status=JobStatus.OPEN,
            # FK refs
            customer_id=data.customer_id,
            vehicle_id=data.vehicle_id,
            booking_id=data.booking_id,
            # Inline details
            customer_name=data.customer_name,
            customer_mobile=data.customer_mobile,
            registration_number=data.registration_number,
            brand=data.brand,
            vehicle_model=data.vehicle_model,
            fuel_type=data.fuel_type,
            odometer_km=data.odometer_km,
            photos=data.photos,
            # Optional shared fields
            description=data.description,
            estimated_amount=data.estimated_amount,
        )
        self.session.add(job)
        await self.session.flush()
        await self._add_timeline(job.id, JobStatus.OPEN, "Job created")
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def update(self, job: Job, data: JobUpdate) -> Job:
        """Apply partial updates for description, photos, inspection, services, labour.

        Uses model_dump_json + json.loads to get JSON-safe Python types (no Decimal
        objects) before handing values to SQLAlchemy JSONB columns.
        """
        import json as _json

        # model_dump_json serialises Decimal → JSON number; json.loads brings back float
        payload: dict = _json.loads(data.model_dump_json(exclude_unset=True))

        for field, value in payload.items():
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

    async def complete(self, job: Job, notes: Optional[str] = None) -> Job:
        """Calculate billing from services + labour, set COMPLETED, store billing JSONB."""
        # ── Billing calculation ──────────────────────────────────────────────
        services_total = Decimal("0.00")
        for item in (job.services or []):
            price = Decimal(str(item.get("price", 0)))
            qty = Decimal(str(item.get("qty", 1)))
            services_total += price * qty

        labour_total = Decimal("0.00")
        if job.labour:
            labour_total = Decimal(str(job.labour.get("charge", 0)))

        subtotal = services_total + labour_total
        gst_amount = (subtotal * _GST_RATE).quantize(Decimal("0.01"))
        grand_total = subtotal + gst_amount

        billing = {
            "services_total": str(services_total.quantize(Decimal("0.01"))),
            "labour_total": str(labour_total.quantize(Decimal("0.01"))),
            "subtotal": str(subtotal.quantize(Decimal("0.01"))),
            "gst_amount": str(gst_amount),
            "grand_total": str(grand_total.quantize(Decimal("0.01"))),
        }

        job.billing = billing
        job.final_amount = float(grand_total.quantize(Decimal("0.01")))
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = job.completed_at
        await self.session.flush()
        await self._add_timeline(job.id, JobStatus.COMPLETED, notes or "Job completed")
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def delete(self, job: Job) -> None:
        job.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
