import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.models.booking import BookingStatus
from app.schemas.booking import BookingDetailResponse, BookingResponse
from app.schemas.customer_workspace import BookingScheduleUpdate
from app.schemas.job import JobResponse
from app.schemas.response import APIResponse, PaginatedData
from app.services.booking_service import BookingService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=APIResponse[PaginatedData[BookingDetailResponse]])
async def list_bookings(
    garage: CurrentGarage,
    session: DBSession,
    status: Optional[BookingStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all bookings for the current garage (paginated)."""
    service = BookingService(session)
    result = await service.list(garage.id, status=status, page=page, page_size=page_size)
    return APIResponse.ok(data=result.model_dump(mode="json"), message="Bookings retrieved")


@router.get("/{booking_id}", response_model=APIResponse[BookingDetailResponse])
async def get_booking(booking_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Get a single booking by ID."""
    service = BookingService(session)
    booking = await service.get(garage.id, booking_id)
    return APIResponse.ok(data=booking.model_dump(mode="json"), message="Booking retrieved")


@router.patch("/{booking_id}/accept", response_model=APIResponse[BookingResponse])
async def accept_booking(booking_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Accept a pending booking."""
    service = BookingService(session)
    booking = await service.accept(garage.id, booking_id)
    return APIResponse.ok(data=booking.model_dump(mode="json"), message="Booking accepted")


@router.patch("/{booking_id}/reject", response_model=APIResponse[BookingResponse])
async def reject_booking(booking_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Reject a pending or accepted booking."""
    service = BookingService(session)
    booking = await service.reject(garage.id, booking_id)
    return APIResponse.ok(data=booking.model_dump(mode="json"), message="Booking rejected")


@router.patch("/{booking_id}/schedule", response_model=APIResponse[BookingResponse])
async def assign_booking_schedule(
    booking_id: uuid.UUID,
    data: BookingScheduleUpdate,
    garage: CurrentGarage,
    session: DBSession,
):
    """Assign or update an appointment time for an accepted booking."""
    service = BookingService(session)
    booking = await service.assign_schedule(
        garage.id, booking_id, data.scheduled_start, data.scheduled_end
    )
    return APIResponse.ok(data=booking.model_dump(mode="json"), message="Booking scheduled")


@router.post("/{booking_id}/create-job", response_model=APIResponse[JobResponse])
async def create_job_from_booking(booking_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Atomically convert a booking into a job and mark the booking as CONVERTED."""
    service = BookingService(session)
    job = await service.create_job_from_booking(garage.id, booking_id)
    return APIResponse.ok(data=job.model_dump(mode="json"), message="Job created from booking")
