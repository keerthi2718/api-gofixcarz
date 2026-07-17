import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.models.job import JobStatus
from app.schemas.job import (
    JobCompleteUpdate,
    JobCreate,
    JobDetailResponse,
    JobResponse,
    JobStatusUpdate,
    JobUpdate,
)
from app.schemas.response import APIResponse, PaginatedData
from app.services.job_service import JobService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=APIResponse[JobResponse], status_code=status.HTTP_201_CREATED)
async def create_job(data: JobCreate, garage: CurrentGarage, session: DBSession):
    """Create a new job (starts in OPEN status)."""
    service = JobService(session)
    job = await service.create(garage.id, data)
    return JSONResponse(
        status_code=201,
        content=APIResponse.created(
            data=job.model_dump(mode="json"),
            message="Job created successfully",
        ).model_dump(),
    )


@router.get("", response_model=APIResponse[PaginatedData[JobResponse]])
async def list_jobs(
    garage: CurrentGarage,
    session: DBSession,
    search: Optional[str] = Query(None, description="Search by job number, customer name, or plate"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    date_from: Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List jobs — paginated, searchable, filterable, sortable."""
    service = JobService(session)
    result = await service.list(
        garage.id,
        search=search,
        status=status,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return APIResponse.ok(data=result.model_dump(mode="json"), message="Jobs retrieved")


@router.get("/{job_id}", response_model=APIResponse[JobDetailResponse])
async def get_job(job_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Get a single job with customer, vehicle, and timeline."""
    service = JobService(session)
    job = await service.get(garage.id, job_id)
    return APIResponse.ok(data=job.model_dump(mode="json"), message="Job retrieved")


@router.put("/{job_id}", response_model=APIResponse[JobResponse])
async def update_job(
    job_id: uuid.UUID, data: JobUpdate, garage: CurrentGarage, session: DBSession
):
    """Update job details (not allowed on completed/cancelled jobs)."""
    service = JobService(session)
    job = await service.update(garage.id, job_id, data)
    return APIResponse.ok(data=job.model_dump(mode="json"), message="Job updated")


@router.patch("/{job_id}/status", response_model=APIResponse[JobResponse])
async def change_job_status(
    job_id: uuid.UUID, data: JobStatusUpdate, garage: CurrentGarage, session: DBSession
):
    """Transition a job to a new status (validates allowed transitions)."""
    service = JobService(session)
    job = await service.change_status(garage.id, job_id, data)
    return APIResponse.ok(data=job.model_dump(mode="json"), message=f"Job status updated to {job.status.value}")


@router.patch("/{job_id}/complete", response_model=APIResponse[JobResponse])
async def complete_job(
    job_id: uuid.UUID, data: JobCompleteUpdate, garage: CurrentGarage, session: DBSession
):
    """Mark a job as COMPLETED, optionally recording the final amount."""
    service = JobService(session)
    job = await service.complete(garage.id, job_id, data)
    return APIResponse.ok(data=job.model_dump(mode="json"), message="Job marked as completed")


@router.delete("/{job_id}", response_model=APIResponse)
async def delete_job(job_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Soft-delete a job."""
    service = JobService(session)
    await service.delete(garage.id, job_id)
    return APIResponse.ok(message="Job deleted")
