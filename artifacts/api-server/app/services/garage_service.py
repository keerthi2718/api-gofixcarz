import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.garage_repository import GarageRepository
from app.schemas.garage import GarageCreate, GarageResponse, GarageUpdate
from app.utils.s3 import generate_download_url


def _with_logo_url(response: GarageResponse) -> GarageResponse:
    """Replace the stored S3 object key with a fresh pre-signed GET URL."""
    if response.logo_url:
        response.logo_url = generate_download_url(response.logo_url)
    return response


class GarageService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = GarageRepository(session)

    async def get(self, user_id: uuid.UUID) -> GarageResponse:
        garage = await self.repo.get_by_user_id(user_id)
        if not garage:
            raise NotFoundException("No garage found for this account")
        return _with_logo_url(GarageResponse.model_validate(garage))

    async def create(self, user_id: uuid.UUID, data: GarageCreate) -> GarageResponse:
        garage = await self.repo.create(user_id, data)
        return _with_logo_url(GarageResponse.model_validate(garage))

    async def update(self, user_id: uuid.UUID, data: GarageUpdate) -> GarageResponse:
        garage = await self.repo.get_by_user_id(user_id)
        if not garage:
            raise NotFoundException("No garage found for this account")
        updated = await self.repo.update(garage, data)
        return _with_logo_url(GarageResponse.model_validate(updated))

    async def update_logo(self, user_id: uuid.UUID, object_key: str) -> GarageResponse:
        """Persist the S3 object key as the garage logo and return a signed URL."""
        garage = await self.repo.get_by_user_id(user_id)
        if not garage:
            raise NotFoundException("No garage found for this account")
        updated = await self.repo.set_logo(garage, object_key)
        return _with_logo_url(GarageResponse.model_validate(updated))
