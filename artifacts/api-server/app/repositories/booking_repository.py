import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, booking: Booking) -> Booking:
        """Persist the shared booking in the caller's transaction.

        Customer links and quote consumption must commit atomically with this
        record; the repository deliberately does not commit independently.
        """
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def get_by_id(
        self, booking_id: uuid.UUID, garage_id: uuid.UUID, load_relations: bool = False
    ) -> Optional[Booking]:
        q = select(Booking).where(
            Booking.id == booking_id,
            Booking.garage_id == garage_id,
            Booking.deleted_at.is_(None),
        )
        if load_relations:
            q = q.options(
                selectinload(Booking.customer),
                selectinload(Booking.vehicle),
            )
        return (await self.session.execute(q)).scalar_one_or_none()

    async def list(
        self,
        garage_id: uuid.UUID,
        status: Optional[BookingStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Booking], int]:
        base_q = select(Booking).where(
            Booking.garage_id == garage_id,
            Booking.deleted_at.is_(None),
        )
        if status:
            base_q = base_q.where(Booking.status == status)

        total: int = (
            await self.session.execute(
                select(func.count()).select_from(base_q.subquery())
            )
        ).scalar_one()

        items_q = (
            base_q.options(
                selectinload(Booking.customer),
                selectinload(Booking.vehicle),
            )
            .order_by(Booking.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(items_q)).scalars().all()
        return list(rows), total

    async def update_status(self, booking: Booking, status: BookingStatus) -> Booking:
        booking.status = status
        booking.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(booking)
        return booking
