from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
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
    """Return the garage linked to the current user.

    `logo_url` in the response is a pre-signed S3 GET URL valid for 1 hour.
    """
    service = GarageService(session)
    garage = await service.get(current_user.id)
    return APIResponse.ok(data=garage.model_dump(mode="json"), message="Garage retrieved")


@router.put("", response_model=APIResponse[GarageResponse])
async def update_garage(data: GarageUpdate, current_user: CurrentUser, session: DBSession):
    """Update garage name, owner, address, working hours, lat/lng, etc."""
    service = GarageService(session)
    garage = await service.update(current_user.id, data)
    return APIResponse.ok(data=garage.model_dump(mode="json"), message="Garage updated")


class LogoSaveRequest(BaseModel):
    object_key: str


@router.post("/logo", response_model=APIResponse[GarageResponse])
async def save_garage_logo(
    data: LogoSaveRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    """Save the S3 object key as the garage logo after a successful upload.

    Upload flow:
    1. Call POST /api/v1/images/upload-url to get a pre-signed PUT URL.
    2. PUT the image binary to that URL directly from the mobile app.
    3. Call this endpoint with the returned object_key to persist the reference.

    The response includes a fresh pre-signed GET URL in `logo_url`.
    """
    service = GarageService(session)
    garage = await service.update_logo(current_user.id, data.object_key)
    return APIResponse.ok(data=garage.model_dump(mode="json"), message="Garage logo updated")
