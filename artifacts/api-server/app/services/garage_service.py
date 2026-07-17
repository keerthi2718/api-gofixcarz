import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.garage_repository import GarageRepository
from app.schemas.garage import GarageCreate, GarageResponse, GarageUpdate


class GarageService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = GarageRepository(session)

    async def get(self, user_id: uuid.UUID) -> GarageResponse:
        garage = await self.repo.get_by_user_id(user_id)
        if not garage:
            raise NotFoundException("No garage found for this account")
        return GarageResponse.model_validate(garage)

    async def create(self, user_id: uuid.UUID, data: GarageCreate) -> GarageResponse:
        garage = await self.repo.create(user_id, data)
        return GarageResponse.model_validate(garage)

    async def update(self, user_id: uuid.UUID, data: GarageUpdate) -> GarageResponse:
        garage = await self.repo.get_by_user_id(user_id)
        if not garage:
            raise NotFoundException("No garage found for this account")
        updated = await self.repo.update(garage, data)
        return GarageResponse.model_validate(updated)
