import uuid
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
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
from app.utils.s3 import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
    generate_download_url,
    generate_upload_url,
    make_object_key,
)

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]

# Allowed extensions mirror the S3 utility's ALLOWED_CONTENT_TYPES
_ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@router.post("/upload-photo", response_model=APIResponse[dict])
async def upload_job_photo(
    garage: CurrentGarage,
    file: UploadFile = File(...),
):
    """Upload a photo for a job and store it in S3.

    Reads the uploaded file, validates type and size, uploads it directly
    to S3 from the server, and returns a pre-signed GET URL valid for 1 hour.
    Store the returned `url` in the job's `photos` list.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_PHOTO_EXTS:
        return JSONResponse(
            status_code=422,
            content=APIResponse(
                success=False,
                message=f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_PHOTO_EXTS)}",
                data=None,
                errors=[],
                status_code=422,
            ).model_dump(),
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        return JSONResponse(
            status_code=413,
            content=APIResponse(
                success=False,
                message="File too large. Maximum size is 5 MB.",
                data=None,
                errors=[],
                status_code=413,
            ).model_dump(),
        )

    # Derive content type from extension
    import mimetypes
    content_type = mimetypes.types_map.get(ext, "image/jpeg")

    # Build S3 key scoped to this garage's job photos
    prefix = f"garages/{garage.id}/job-photos"
    object_key, _ = make_object_key(prefix, file.filename or f"photo{ext}")

    # Upload directly to S3 from the server
    import boto3
    from app.core.config import settings
    s3 = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_API_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
    )
    s3.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=object_key,
        Body=contents,
        ContentType=content_type,
    )

    # Return a pre-signed download URL (1 hour)
    url = generate_download_url(object_key)
    return APIResponse.ok(
        data={"url": url, "object_key": object_key},
        message="Photo uploaded",
    )


@router.post("", response_model=APIResponse[JobResponse], status_code=status.HTTP_201_CREATED)
async def create_job(data: JobCreate, garage: CurrentGarage, session: DBSession):
    """Create a new job (starts in OPEN status).

    Pass either `customer_id` + `vehicle_id` (for booking-based creation) or
    the full inline details: `customer_name`, `customer_mobile`,
    `registration_number`, `brand`, `vehicle_model`, `fuel_type`, `odometer_km`.
    """
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
    search: Optional[str] = Query(None, description="Search by job number, customer name, plate, or registration"),
    status_filter: Optional[JobStatus] = Query(None, alias="status_filter", description="Filter by status (OPEN, IN_PROGRESS, WAITING_FOR_PARTS, QUALITY_CHECK, READY, COMPLETED, CANCELLED)"),
    # Legacy alias kept for backwards compatibility
    status: Optional[JobStatus] = Query(None, description="Filter by status (deprecated, use status_filter)"),
    date_from: Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List jobs — paginated, searchable, filterable by status, sortable."""
    effective_status = status_filter or status
    svc = JobService(session)
    result = await svc.list(
        garage.id,
        search=search,
        status=effective_status,
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
    """Get a single job with inline details, customer/vehicle (if FK linked), and timeline."""
    svc = JobService(session)
    job = await svc.get(garage.id, job_id)
    return APIResponse.ok(data=job.model_dump(mode="json"), message="Job retrieved")


@router.put("/{job_id}", response_model=APIResponse[JobResponse])
async def update_job(
    job_id: uuid.UUID, data: JobUpdate, garage: CurrentGarage, session: DBSession
):
    """Update inspection, services, labour, photos, or description.

    Only the fields you include in the request body are changed; everything
    else stays as-is.  Not allowed on completed or cancelled jobs.
    """
    svc = JobService(session)
    job = await svc.update(garage.id, job_id, data)
    return APIResponse.ok(data=job.model_dump(mode="json"), message="Job updated")


@router.patch("/{job_id}/status", response_model=APIResponse[JobResponse])
async def change_job_status(
    job_id: uuid.UUID, data: JobStatusUpdate, garage: CurrentGarage, session: DBSession
):
    """Transition job to a new status. Each transition appends a timeline entry.

    Valid transitions:
    - OPEN → IN_PROGRESS, CANCELLED
    - IN_PROGRESS → WAITING_FOR_PARTS, QUALITY_CHECK, READY, COMPLETED, CANCELLED
    - WAITING_FOR_PARTS → IN_PROGRESS, CANCELLED
    - QUALITY_CHECK → IN_PROGRESS, READY, COMPLETED, CANCELLED
    - READY → COMPLETED, CANCELLED
    """
    svc = JobService(session)
    job = await svc.change_status(garage.id, job_id, data)
    return APIResponse.ok(data=job.model_dump(mode="json"), message=f"Job status updated to {job.status.value}")


@router.patch("/{job_id}/complete", response_model=APIResponse[JobResponse])
async def complete_job(
    job_id: uuid.UUID, data: JobCompleteUpdate, garage: CurrentGarage, session: DBSession
):
    """Mark a job as COMPLETED and calculate final billing.

    Billing breakdown (stored in `billing` field):
    - services_total = Σ(price × qty) for each service item
    - labour_total = labour.charge
    - subtotal = services_total + labour_total
    - gst_amount = subtotal × 18%
    - grand_total = subtotal + gst_amount

    All monetary values are returned with exactly 2 decimal places.
    """
    svc = JobService(session)
    job = await svc.complete(garage.id, job_id, data)
    return APIResponse.ok(data=job.model_dump(mode="json"), message="Job marked as completed")


@router.delete("/{job_id}", response_model=APIResponse)
async def delete_job(job_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Soft-delete a job."""
    svc = JobService(session)
    await svc.delete(garage.id, job_id)
    return APIResponse.ok(message="Job deleted")
