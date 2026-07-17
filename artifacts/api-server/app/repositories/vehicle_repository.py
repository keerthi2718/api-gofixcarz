import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate


class VehicleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, vehicle_id: uuid.UUID, garage_id: uuid.UUID, load_customer: bool = False
    ) -> Optional[Vehicle]:
        q = select(Vehicle).where(
            Vehicle.id == vehicle_id,
            Vehicle.garage_id == garage_id,
            Vehicle.deleted_at.is_(None),
        )
        if load_customer:
            q = q.options(selectinload(Vehicle.customer))
        result = await self.session.execute(q)
        return result.scalar_one_or_none()

    async def list(
        self,
        garage_id: uuid.UUID,
        customer_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Vehicle], int]:
        base_q = select(Vehicle).where(
            Vehicle.garage_id == garage_id,
            Vehicle.deleted_at.is_(None),
        )
        if customer_id:
            base_q = base_q.where(Vehicle.customer_id == customer_id)
        if search:
            term = f"%{search}%"
            base_q = base_q.where(
                Vehicle.registration_plate.ilike(term)
                | Vehicle.make.ilike(term)
                | Vehicle.model.ilike(term)
            )

        count_q = select(func.count()).select_from(base_q.subquery())
        total: int = (await self.session.execute(count_q)).scalar_one()

        items_q = (
            base_q
            .order_by(Vehicle.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(items_q)).scalars().all()
        return list(rows), total

    async def create(
        self, garage_id: uuid.UUID, data: VehicleCreate
    ) -> Vehicle:
        vehicle = Vehicle(
            id=uuid.uuid4(),
            garage_id=garage_id,
            **data.model_dump(),
        )
        self.session.add(vehicle)
        await self.session.flush()
        await self.session.refresh(vehicle)
        return vehicle

    async def update(self, vehicle: Vehicle, data: VehicleUpdate) -> Vehicle:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(vehicle, field, value)
        vehicle.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(vehicle)
        return vehicle

    async def delete(self, vehicle: Vehicle) -> None:
        vehicle.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
