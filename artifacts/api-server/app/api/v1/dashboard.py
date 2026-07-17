from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.schemas.dashboard import DashboardResponse
from app.schemas.response import APIResponse
from app.services.dashboard_service import DashboardService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=APIResponse[DashboardResponse])
async def get_dashboard(garage: CurrentGarage, session: DBSession):
    """Return today's KPIs and recent activity for the current garage."""
    service = DashboardService(session)
    data = await service.get(garage.id)
    return APIResponse.ok(data=data.model_dump(mode="json"), message="Dashboard data retrieved")
