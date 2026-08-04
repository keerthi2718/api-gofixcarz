import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.garage import Garage
from app.schemas.garage import GarageCreate, GarageUpdate


class GarageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[Garage]:
        result = await self.session.execute(
            select(Garage).where(
                Garage.user_id == user_id,
                Garage.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, garage_id: uuid.UUID) -> Optional[Garage]:
        result = await self.session.execute(
            select(Garage).where(
                Garage.id == garage_id,
                Garage.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: uuid.UUID, data: GarageCreate) -> Garage:
        garage = Garage(
            id=uuid.uuid4(),
            user_id=user_id,
            **data.model_dump(),
        )
        self.session.add(garage)
        await self.session.flush()
        await self.session.refresh(garage)
        return garage

    async def update(self, garage: Garage, data: GarageUpdate) -> Garage:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(garage, field, value)
        garage.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(garage)
        return garage

    async def set_logo(self, garage: Garage, object_key: str) -> Garage:
        """Store the S3 object key as the garage logo."""
        garage.logo_url = object_key
        garage.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(garage)
        return garage
