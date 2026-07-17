import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification import NotificationResponse
from app.schemas.response import PaginatedData


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = NotificationRepository(session)

    async def list(
        self,
        garage_id: uuid.UUID,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedData[NotificationResponse]:
        page_size = min(page_size, 100)
        items, total = await self.repo.list(
            garage_id, unread_only=unread_only, page=page, page_size=page_size
        )
        return PaginatedData(
            items=[NotificationResponse.from_orm_with_read(n) for n in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    async def mark_read(self, garage_id: uuid.UUID, notif_id: uuid.UUID) -> NotificationResponse:
        notif = await self.repo.get_by_id(notif_id, garage_id)
        if not notif:
            raise NotFoundException("Notification not found")
        updated = await self.repo.mark_read(notif)
        return NotificationResponse.from_orm_with_read(updated)
