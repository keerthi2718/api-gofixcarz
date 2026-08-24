import uuid
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.garage import Garage
from app.models.job import JobStatus
from app.repositories.customer_repository import CustomerRepository
from app.repositories.job_repository import JobRepository
from app.repositories.vehicle_repository import VehicleRepository
from app.schemas.job import (
    JobCompleteUpdate,
    JobCreate,
    JobDetailResponse,
    JobResponse,
    JobStatusUpdate,
    JobUpdate,
)
from app.schemas.response import PaginatedData
from app.services.image_lifecycle_service import ImageLifecycleService
from app.utils.s3 import generate_download_url, is_garage_object_key

# Terminal statuses — no further transitions allowed
_TERMINAL = {JobStatus.COMPLETED, JobStatus.CANCELLED}

# Allowed transitions: from -> set of valid next statuses
_VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.OPEN:              {JobStatus.IN_PROGRESS, JobStatus.CANCELLED},
    JobStatus.IN_PROGRESS:       {JobStatus.WAITING_FOR_PARTS, JobStatus.QUALITY_CHECK, JobStatus.READY, JobStatus.COMPLETED, JobStatus.CANCELLED},
    JobStatus.WAITING_FOR_PARTS: {JobStatus.IN_PROGRESS, JobStatus.CANCELLED},
    JobStatus.QUALITY_CHECK:     {JobStatus.IN_PROGRESS, JobStatus.READY, JobStatus.COMPLETED, JobStatus.CANCELLED},
    JobStatus.READY:             {JobStatus.COMPLETED, JobStatus.CANCELLED},
    JobStatus.COMPLETED:         set(),
    JobStatus.CANCELLED:         set(),
}


def _with_photo_urls(response: JobResponse | JobDetailResponse) -> JobResponse | JobDetailResponse:
    """Expose each stored object key with a fresh signed read URL."""
    if response.photos is not None:
        response.photos = [
            {
                "object_key": key,
                "url": (
                    generate_download_url(key)
                    if isinstance(key, str) and is_garage_object_key(key, response.garage_id)
                    else None
                ),
            }
            for key in response.photos
        ]
    return response


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = JobRepository(session)
        self.customer_repo = CustomerRepository(session)
        self.vehicle_repo = VehicleRepository(session)

    async def create(self, garage_id: uuid.UUID, data: JobCreate) -> JobResponse:
        """Create a job.

        Two paths:
        - FK path (booking flow): customer_id + vehicle_id present → validate them.
        - Direct path: inline customer/vehicle details → no FK lookup needed.
        """
        if data.customer_id and data.vehicle_id:
            customer = await self.customer_repo.get_by_id(data.customer_id, garage_id)
            if not customer:
                raise NotFoundException("Customer not found")
            vehicle = await self.vehicle_repo.get_by_id(data.vehicle_id, garage_id)
            if not vehicle:
                raise NotFoundException("Vehicle not found")

        lifecycle = ImageLifecycleService(self.repo.session)
        await lifecycle.validate_object_keys(garage_id, data.photos)
        job = await self.repo.create(garage_id, data)
        return _with_photo_urls(JobResponse.model_validate(job))

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
    ) -> PaginatedData[JobResponse]:
        page_size = min(page_size, 100)

        allowed_sort_fields = {"created_at", "updated_at", "job_number", "status", "estimated_amount", "final_amount"}
        if sort_by not in allowed_sort_fields:
            sort_by = "created_at"
        if sort_dir.lower() not in ("asc", "desc"):
            sort_dir = "desc"

        items, total = await self.repo.list(
            garage_id,
            search=search,
            status=status,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
        return PaginatedData(
            items=[_with_photo_urls(JobResponse.model_validate(j)) for j in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    async def get(self, garage_id: uuid.UUID, job_id: uuid.UUID) -> JobDetailResponse:
        job = await self.repo.get_by_id(job_id, garage_id, load_relations=True)
        if not job:
            raise NotFoundException("Job not found")
        return _with_photo_urls(JobDetailResponse.model_validate(job))

    async def update(
        self, garage_id: uuid.UUID, job_id: uuid.UUID, data: JobUpdate
    ) -> JobResponse:
        job = await self.repo.get_by_id(job_id, garage_id)
        if not job:
            raise NotFoundException("Job not found")
        if job.status in _TERMINAL:
            raise BadRequestException(
                f"Cannot edit a job that is {job.status.value}."
            )
        lifecycle = ImageLifecycleService(self.repo.session)
        photos_are_updated = "photos" in data.model_fields_set
        previous_keys = {
            key for key in (job.photos or []) if isinstance(key, str)
        }
        if photos_are_updated:
            await lifecycle.validate_object_keys(garage_id, data.photos)

        updated = await self.repo.update(job, data)
        if photos_are_updated:
            # Persist the replacement list before removing objects that are no
            # longer referenced. This prevents a DB failure from losing images.
            await self.repo.session.commit()
            garage = await self.repo.session.get(Garage, garage_id)
            if garage:
                for object_key in previous_keys - set(data.photos or []):
                    await lifecycle.delete_if_unreferenced(garage, object_key)
        return _with_photo_urls(JobResponse.model_validate(updated))

    async def change_status(
        self, garage_id: uuid.UUID, job_id: uuid.UUID, data: JobStatusUpdate
    ) -> JobResponse:
        job = await self.repo.get_by_id(job_id, garage_id)
        if not job:
            raise NotFoundException("Job not found")
        if job.status in _TERMINAL:
            raise BadRequestException(
                f"Job is already {job.status.value} and cannot be transitioned."
            )
        allowed = _VALID_TRANSITIONS.get(job.status, set())
        if data.status not in allowed:
            raise BadRequestException(
                f"Cannot transition from {job.status.value} to {data.status.value}. "
                f"Allowed: {', '.join(s.value for s in allowed) or 'none'}."
            )
        updated = await self.repo.change_status(job, data.status, data.notes)
        return _with_photo_urls(JobResponse.model_validate(updated))

    async def complete(
        self, garage_id: uuid.UUID, job_id: uuid.UUID, data: JobCompleteUpdate
    ) -> JobResponse:
        job = await self.repo.get_by_id(job_id, garage_id)
        if not job:
            raise NotFoundException("Job not found")
        if job.status == JobStatus.COMPLETED:
            raise BadRequestException("Job is already completed.")
        if job.status == JobStatus.CANCELLED:
            raise BadRequestException("Cannot complete a cancelled job.")
        updated = await self.repo.complete(job, data.notes)
        return _with_photo_urls(JobResponse.model_validate(updated))

    async def delete(self, garage_id: uuid.UUID, job_id: uuid.UUID) -> None:
        job = await self.repo.get_by_id(job_id, garage_id)
        if not job:
            raise NotFoundException("Job not found")
        photo_keys = {key for key in (job.photos or []) if isinstance(key, str)}
        await self.repo.delete(job)
        # This app soft-deletes jobs, so remove their images after the soft
        # delete has committed. Unreferenced checks protect reused keys.
        await self.repo.session.commit()
        garage = await self.repo.session.get(Garage, garage_id)
        if garage:
            lifecycle = ImageLifecycleService(self.repo.session)
            for object_key in photo_keys:
                await lifecycle.delete_if_unreferenced(garage, object_key)
