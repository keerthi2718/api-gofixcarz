import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from app.schemas.response import PaginatedData


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = CustomerRepository(session)

    async def create(self, garage_id: uuid.UUID, data: CustomerCreate) -> CustomerResponse:
        customer = await self.repo.create(garage_id, data)
        return CustomerResponse.model_validate(customer)

    async def list(
        self,
        garage_id: uuid.UUID,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedData[CustomerResponse]:
        page_size = min(page_size, 100)
        items, total = await self.repo.list(garage_id, search=search, page=page, page_size=page_size)
        return PaginatedData(
            items=[CustomerResponse.model_validate(c) for c in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),  # ceiling division
        )

    async def get(self, garage_id: uuid.UUID, customer_id: uuid.UUID) -> CustomerResponse:
        customer = await self.repo.get_by_id(customer_id, garage_id)
        if not customer:
            raise NotFoundException("Customer not found")
        return CustomerResponse.model_validate(customer)

    async def update(
        self, garage_id: uuid.UUID, customer_id: uuid.UUID, data: CustomerUpdate
    ) -> CustomerResponse:
        customer = await self.repo.get_by_id(customer_id, garage_id)
        if not customer:
            raise NotFoundException("Customer not found")
        updated = await self.repo.update(customer, data)
        return CustomerResponse.model_validate(updated)

    async def delete(self, garage_id: uuid.UUID, customer_id: uuid.UUID) -> None:
        customer = await self.repo.get_by_id(customer_id, garage_id)
        if not customer:
            raise NotFoundException("Customer not found")
        await self.repo.delete(customer)
