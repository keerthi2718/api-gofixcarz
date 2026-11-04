import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.booking import Booking, BookingStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.job_repository import JobRepository
from app.schemas.booking import BookingDetailResponse, BookingResponse
from app.schemas.job import JobCreate, JobResponse
from app.schemas.response import PaginatedData


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = BookingRepository(session)
        self.job_repo = JobRepository(session)

    async def list(
        self,
        garage_id: uuid.UUID,
        status: Optional[BookingStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedData[BookingDetailResponse]:
        page_size = min(page_size, 100)
        items, total = await self.repo.list(garage_id, status=status, page=page, page_size=page_size)
        return PaginatedData(
            items=[BookingDetailResponse.model_validate(b) for b in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    async def get(self, garage_id: uuid.UUID, booking_id: uuid.UUID) -> BookingDetailResponse:
        booking = await self.repo.get_by_id(booking_id, garage_id, load_relations=True)
        if not booking:
            raise NotFoundException("Booking not found")
        return BookingDetailResponse.model_validate(booking)

    async def accept(self, garage_id: uuid.UUID, booking_id: uuid.UUID) -> BookingResponse:
        from app.services.admin_booking_history import ensure_new_work, lock_booking, record_booking_event
        await ensure_new_work(self.repo.session, garage_id)
        await lock_booking(self.repo.session, garage_id, booking_id)
        booking = await self.repo.get_by_id(booking_id, garage_id)
        if not booking:
            raise NotFoundException("Booking not found")
        if booking.status != BookingStatus.PENDING:
            raise BadRequestException(f"Only PENDING bookings can be accepted (current: {booking.status.value})")
        from app.services.customer_booking_guards import validate_customer_appointment
        await validate_customer_appointment(self.repo.session, booking)
        updated = await self.repo.update_status(booking, BookingStatus.ACCEPTED)
        await record_booking_event(self.repo.session, updated, "ACCEPTED")
        return BookingResponse.model_validate(updated)

    async def reject(self, garage_id: uuid.UUID, booking_id: uuid.UUID) -> BookingResponse:
        from app.services.admin_booking_history import lock_booking, record_booking_event
        await lock_booking(self.repo.session, garage_id, booking_id)
        booking = await self.repo.get_by_id(booking_id, garage_id)
        if not booking:
            raise NotFoundException("Booking not found")
        if booking.status not in (BookingStatus.PENDING, BookingStatus.ACCEPTED):
            raise BadRequestException(
                f"Cannot reject a booking with status {booking.status.value}"
            )
        updated = await self.repo.update_status(booking, BookingStatus.REJECTED)
        await record_booking_event(self.repo.session, updated, "REJECTED")
        return BookingResponse.model_validate(updated)

    async def create_job_from_booking(
        self, garage_id: uuid.UUID, booking_id: uuid.UUID
    ) -> JobResponse:
        from app.services.admin_booking_history import ensure_new_work, lock_booking
        await lock_booking(self.repo.session, garage_id, booking_id)
        booking = await self.repo.get_by_id(booking_id, garage_id, load_relations=True)
        if not booking:
            raise NotFoundException("Booking not found")
        if booking.status not in (BookingStatus.PENDING, BookingStatus.ACCEPTED):
            raise BadRequestException("Only PENDING or ACCEPTED bookings may be converted to jobs")
        # Conversion of previously accepted work remains allowed while suspended.
        if booking.status == BookingStatus.PENDING:
            await ensure_new_work(self.repo.session, garage_id)
            from app.services.customer_booking_guards import validate_customer_appointment
            await validate_customer_appointment(self.repo.session, booking)
        if not booking.customer_id or not booking.vehicle_id:
            raise BadRequestException(
                "Booking must have a linked customer and vehicle to create a job"
            )

        # Create the job (same transaction — session.flush() keeps it atomic)
        job_data = JobCreate(
            customer_id=booking.customer_id,
            vehicle_id=booking.vehicle_id,
            booking_id=booking.id,
            description=booking.service_requested,
        )
        job = await self.job_repo.create(garage_id, job_data)

        # Mark booking as CONVERTED
        await self.repo.update_status(booking, BookingStatus.CONVERTED)
        from app.services.admin_booking_history import record_booking_event
        await record_booking_event(self.repo.session, booking, "CONVERTED")
        from app.services.customer_events import customer_job_event
        await customer_job_event(self.repo.session, job)

        return JobResponse.model_validate(job)
