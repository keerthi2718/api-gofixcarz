import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.garage_repository import GarageRepository
from app.schemas.garage import GarageCreate, GarageResponse, GarageUpdate
from app.services.image_lifecycle_service import ImageLifecycleService
from app.utils.s3 import generate_download_url, is_garage_object_key


def _with_logo_url(response: GarageResponse) -> GarageResponse:
    """Expose both the stored key and a fresh signed GET URL."""
    if response.logo_url:
        response.logo_object_key = response.logo_url
        if is_garage_object_key(response.logo_url, response.id):
            response.logo_url = generate_download_url(response.logo_url)
        else:
            response.logo_url = None
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
        """Validate and persist a logo key, then clean up the replaced object."""
        garage = await self.repo.get_by_user_id(user_id)
        if not garage:
            raise NotFoundException("No garage found for this account")

        lifecycle = ImageLifecycleService(self.repo.session)
        await lifecycle.validate_object_keys(garage.id, [object_key])
        previous_key = garage.logo_url
        updated = await self.repo.set_logo(garage, object_key)
        # Commit before deleting the old S3 object so a failed DB write never
        # destroys the logo currently referenced by the garage.
        await self.repo.session.commit()
        if previous_key and previous_key != object_key:
            await lifecycle.delete_if_unreferenced(updated, previous_key)
        return _with_logo_url(GarageResponse.model_validate(updated))
