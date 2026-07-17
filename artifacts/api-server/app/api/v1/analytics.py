from datetime import date
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.schemas.analytics import AnalyticsResponse
from app.schemas.response import APIResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=APIResponse[AnalyticsResponse])
async def get_analytics(
    garage: CurrentGarage,
    session: DBSession,
    period: str = Query("monthly", description="daily | weekly | monthly | custom"),
    start_date: Optional[date] = Query(None, description="Required for period=custom"),
    end_date: Optional[date] = Query(None, description="Required for period=custom"),
):
    """Revenue, job counts, and time-series graph data."""
    if period not in ("daily", "weekly", "monthly", "custom"):
        raise BadRequestException("period must be one of: daily, weekly, monthly, custom")
    if period == "custom" and (not start_date or not end_date):
        raise BadRequestException("start_date and end_date are required for period=custom")
    if start_date and end_date and start_date > end_date:
        raise BadRequestException("start_date must be before end_date")

    service = AnalyticsService(session)
    data = await service.get(garage.id, period=period, start_date=start_date, end_date=end_date)
    return APIResponse.ok(data=data.model_dump(mode="json"), message="Analytics retrieved")
