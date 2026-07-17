import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, customer_id: uuid.UUID, garage_id: uuid.UUID) -> Optional[Customer]:
        result = await self.session.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.garage_id == garage_id,
                Customer.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        garage_id: uuid.UUID,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Customer], int]:
        base_q = select(Customer).where(
            Customer.garage_id == garage_id,
            Customer.deleted_at.is_(None),
        )
        if search:
            term = f"%{search}%"
            base_q = base_q.where(
                Customer.name.ilike(term) | Customer.mobile.ilike(term)
            )

        count_q = select(func.count()).select_from(base_q.subquery())
        total: int = (await self.session.execute(count_q)).scalar_one()

        items_q = (
            base_q
            .order_by(Customer.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(items_q)).scalars().all()
        return list(rows), total

    async def create(self, garage_id: uuid.UUID, data: CustomerCreate) -> Customer:
        customer = Customer(
            id=uuid.uuid4(),
            garage_id=garage_id,
            **data.model_dump(),
        )
        self.session.add(customer)
        await self.session.flush()
        await self.session.refresh(customer)
        return customer

    async def update(self, customer: Customer, data: CustomerUpdate) -> Customer:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(customer, field, value)
        customer.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(customer)
        return customer

    async def delete(self, customer: Customer) -> None:
        customer.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
