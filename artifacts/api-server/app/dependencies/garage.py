"""Garage dependency — resolves the active garage for the current user."""
import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.database.session import get_session
from app.dependencies.auth import get_current_user
from app.models.garage import Garage
from app.models.user import User


async def get_current_garage(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Garage:
    """Return the active garage owned by the current user."""
    result = await session.execute(
        select(Garage).where(
            Garage.user_id == current_user.id,
            Garage.deleted_at.is_(None),
        )
    )
    garage = result.scalar_one_or_none()
    if not garage:
        raise NotFoundException(
            "No garage found for this account. Please set up your garage first."
        )
    return garage


CurrentGarage = Annotated[Garage, Depends(get_current_garage)]
