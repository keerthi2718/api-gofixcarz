from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.auth import CurrentUser
from app.schemas.garage import GarageResponse, GarageUpdate
from app.schemas.response import APIResponse
from app.services.garage_service import GarageService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=APIResponse[GarageResponse])
async def get_garage(current_user: CurrentUser, session: DBSession):
    """Return the garage linked to the current user."""
    service = GarageService(session)
    garage = await service.get(current_user.id)
    return APIResponse.ok(data=garage.model_dump(mode="json"), message="Garage retrieved")


@router.put("", response_model=APIResponse[GarageResponse])
async def update_garage(data: GarageUpdate, current_user: CurrentUser, session: DBSession):
    """Update garage name, owner, address, working hours, lat/lng, etc."""
    service = GarageService(session)
    garage = await service.update(current_user.id, data)
    return APIResponse.ok(data=garage.model_dump(mode="json"), message="Garage updated")
