import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, notif_id: uuid.UUID, garage_id: uuid.UUID
    ) -> Optional[Notification]:
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notif_id,
                Notification.garage_id == garage_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        garage_id: uuid.UUID,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        base_q = select(Notification).where(Notification.garage_id == garage_id)
        if unread_only:
            base_q = base_q.where(Notification.read_at.is_(None))

        total: int = (
            await self.session.execute(
                select(func.count()).select_from(base_q.subquery())
            )
        ).scalar_one()

        # Unread first, then by created_at desc
        items_q = (
            base_q.order_by(
                Notification.read_at.is_(None).desc(),
                Notification.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(items_q)).scalars().all()
        return list(rows), total

    async def mark_read(self, notif: Notification) -> Notification:
        notif.read_at = datetime.now(timezone.utc)
        notif.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(notif)
        return notif

    async def create(
        self,
        garage_id: uuid.UUID,
        title: str,
        message: str,
        type: Optional[str] = None,
        reference_id: Optional[uuid.UUID] = None,
    ) -> Notification:
        notif = Notification(
            id=uuid.uuid4(),
            garage_id=garage_id,
            title=title,
            message=message,
            type=type,
            reference_id=reference_id,
        )
        self.session.add(notif)
        await self.session.flush()
        return notif
