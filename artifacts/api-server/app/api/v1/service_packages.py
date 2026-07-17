import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.schemas.response import APIResponse, PaginatedData
from app.schemas.service_package import (
    ServicePackageCreate,
    ServicePackageResponse,
    ServicePackageUpdate,
)
from app.services.service_package_service import ServicePackageService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=APIResponse[ServicePackageResponse], status_code=status.HTTP_201_CREATED)
async def create_package(data: ServicePackageCreate, garage: CurrentGarage, session: DBSession):
    """Create a new service package."""
    service = ServicePackageService(session)
    pkg = await service.create(garage.id, data)
    return JSONResponse(
        status_code=201,
        content=APIResponse.created(
            data=pkg.model_dump(mode="json"), message="Service package created"
        ).model_dump(),
    )


@router.get("", response_model=APIResponse[PaginatedData[ServicePackageResponse]])
async def list_packages(
    garage: CurrentGarage,
    session: DBSession,
    search: Optional[str] = Query(None),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List service packages (paginated)."""
    service = ServicePackageService(session)
    result = await service.list(
        garage.id, search=search, active_only=active_only, page=page, page_size=page_size
    )
    return APIResponse.ok(data=result.model_dump(mode="json"), message="Service packages retrieved")


@router.get("/{pkg_id}", response_model=APIResponse[ServicePackageResponse])
async def get_package(pkg_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Get a single service package."""
    service = ServicePackageService(session)
    pkg = await service.get(garage.id, pkg_id)
    return APIResponse.ok(data=pkg.model_dump(mode="json"), message="Service package retrieved")


@router.put("/{pkg_id}", response_model=APIResponse[ServicePackageResponse])
async def update_package(
    pkg_id: uuid.UUID, data: ServicePackageUpdate, garage: CurrentGarage, session: DBSession
):
    """Update a service package."""
    service = ServicePackageService(session)
    pkg = await service.update(garage.id, pkg_id, data)
    return APIResponse.ok(data=pkg.model_dump(mode="json"), message="Service package updated")


@router.delete("/{pkg_id}", response_model=APIResponse)
async def delete_package(pkg_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Soft-delete a service package."""
    service = ServicePackageService(session)
    await service.delete(garage.id, pkg_id)
    return APIResponse.ok(message="Service package deleted")
