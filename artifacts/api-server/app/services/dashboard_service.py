import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import DashboardResponse, RecentActivity


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = DashboardRepository(session)

    async def get(self, garage_id: uuid.UUID) -> DashboardResponse:
        data = await self.repo.get_summary(garage_id)
        return DashboardResponse(
            jobs_today=data["jobs_today"],
            open_jobs=data["open_jobs"],
            in_progress_jobs=data["in_progress_jobs"],
            completed_jobs=data["completed_jobs"],
            cancelled_jobs=data["cancelled_jobs"],
            bookings_today=data["bookings_today"],
            pending_bookings=data["pending_bookings"],
            revenue_today=Decimal(str(data["revenue_today"])),
            revenue_this_month=Decimal(str(data["revenue_this_month"])),
            recent_activities=[RecentActivity(**a) for a in data["recent_activities"]],
        )
