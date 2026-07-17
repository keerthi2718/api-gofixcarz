from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.auth import CurrentUser
from app.schemas.profile import ProfileResponse, ProfileUpdate
from app.schemas.response import APIResponse
from app.services.profile_service import ProfileService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=APIResponse[ProfileResponse])
async def get_profile(current_user: CurrentUser, session: DBSession):
    """Return the authenticated user's profile."""
    service = ProfileService(session)
    profile = await service.get(current_user.id)
    return APIResponse.ok(data=profile.model_dump(mode="json"), message="Profile retrieved")


@router.put("", response_model=APIResponse[ProfileResponse])
async def update_profile(data: ProfileUpdate, current_user: CurrentUser, session: DBSession):
    """Update name, email, or mobile for the authenticated user."""
    service = ProfileService(session)
    profile = await service.update(current_user.id, data)
    return APIResponse.ok(data=profile.model_dump(mode="json"), message="Profile updated")
