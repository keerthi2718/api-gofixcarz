import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.schemas.notification import NotificationResponse
from app.schemas.response import APIResponse, PaginatedData
from app.services.notification_service import NotificationService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=APIResponse[PaginatedData[NotificationResponse]])
async def list_notifications(
    garage: CurrentGarage,
    session: DBSession,
    unread_only: bool = Query(False, description="Return only unread notifications"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List notifications for the current garage (unread first)."""
    service = NotificationService(session)
    result = await service.list(garage.id, unread_only=unread_only, page=page, page_size=page_size)
    return APIResponse.ok(data=result.model_dump(mode="json"), message="Notifications retrieved")


@router.patch("/{notif_id}/read", response_model=APIResponse[NotificationResponse])
async def mark_notification_read(notif_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Mark a notification as read."""
    service = NotificationService(session)
    notif = await service.mark_read(garage.id, notif_id)
    return APIResponse.ok(data=notif.model_dump(mode="json"), message="Notification marked as read")
