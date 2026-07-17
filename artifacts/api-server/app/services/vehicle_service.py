import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.vehicle_repository import VehicleRepository
from app.repositories.customer_repository import CustomerRepository
from app.schemas.vehicle import VehicleCreate, VehicleDetailResponse, VehicleResponse, VehicleUpdate
from app.schemas.response import PaginatedData


class VehicleService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = VehicleRepository(session)
        self.customer_repo = CustomerRepository(session)

    async def create(self, garage_id: uuid.UUID, data: VehicleCreate) -> VehicleResponse:
        # Verify the customer belongs to this garage
        customer = await self.customer_repo.get_by_id(data.customer_id, garage_id)
        if not customer:
            raise NotFoundException("Customer not found")
        vehicle = await self.repo.create(garage_id, data)
        return VehicleResponse.model_validate(vehicle)

    async def list(
        self,
        garage_id: uuid.UUID,
        customer_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedData[VehicleResponse]:
        page_size = min(page_size, 100)
        items, total = await self.repo.list(
            garage_id, customer_id=customer_id, search=search, page=page, page_size=page_size
        )
        return PaginatedData(
            items=[VehicleResponse.model_validate(v) for v in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    async def get(self, garage_id: uuid.UUID, vehicle_id: uuid.UUID) -> VehicleDetailResponse:
        vehicle = await self.repo.get_by_id(vehicle_id, garage_id, load_customer=True)
        if not vehicle:
            raise NotFoundException("Vehicle not found")
        return VehicleDetailResponse.model_validate(vehicle)

    async def update(
        self, garage_id: uuid.UUID, vehicle_id: uuid.UUID, data: VehicleUpdate
    ) -> VehicleResponse:
        vehicle = await self.repo.get_by_id(vehicle_id, garage_id)
        if not vehicle:
            raise NotFoundException("Vehicle not found")
        # If reassigning customer, verify the new customer belongs to this garage
        if data.customer_id is not None:
            customer = await self.customer_repo.get_by_id(data.customer_id, garage_id)
            if not customer:
                raise NotFoundException("Customer not found")
        updated = await self.repo.update(vehicle, data)
        return VehicleResponse.model_validate(updated)

    async def delete(self, garage_id: uuid.UUID, vehicle_id: uuid.UUID) -> None:
        vehicle = await self.repo.get_by_id(vehicle_id, garage_id)
        if not vehicle:
            raise NotFoundException("Vehicle not found")
        await self.repo.delete(vehicle)
