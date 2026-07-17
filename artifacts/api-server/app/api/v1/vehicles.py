import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.schemas.vehicle import VehicleCreate, VehicleDetailResponse, VehicleResponse, VehicleUpdate
from app.schemas.response import APIResponse, PaginatedData
from app.services.vehicle_service import VehicleService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=APIResponse[VehicleResponse], status_code=status.HTTP_201_CREATED)
async def create_vehicle(data: VehicleCreate, garage: CurrentGarage, session: DBSession):
    """Create a new vehicle linked to a customer."""
    service = VehicleService(session)
    vehicle = await service.create(garage.id, data)
    return JSONResponse(
        status_code=201,
        content=APIResponse.created(
            data=vehicle.model_dump(mode="json"),
            message="Vehicle created successfully",
        ).model_dump(),
    )


@router.get("", response_model=APIResponse[PaginatedData[VehicleResponse]])
async def list_vehicles(
    garage: CurrentGarage,
    session: DBSession,
    customer_id: Optional[uuid.UUID] = Query(None, description="Filter by customer"),
    search: Optional[str] = Query(None, description="Search by plate, make, or model"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all vehicles for the current garage (paginated)."""
    service = VehicleService(session)
    result = await service.list(
        garage.id, customer_id=customer_id, search=search, page=page, page_size=page_size
    )
    return APIResponse.ok(data=result.model_dump(mode="json"), message="Vehicles retrieved")


@router.get("/{vehicle_id}", response_model=APIResponse[VehicleDetailResponse])
async def get_vehicle(vehicle_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Get a single vehicle by ID (includes customer info)."""
    service = VehicleService(session)
    vehicle = await service.get(garage.id, vehicle_id)
    return APIResponse.ok(data=vehicle.model_dump(mode="json"), message="Vehicle retrieved")


@router.put("/{vehicle_id}", response_model=APIResponse[VehicleResponse])
async def update_vehicle(
    vehicle_id: uuid.UUID, data: VehicleUpdate, garage: CurrentGarage, session: DBSession
):
    """Update a vehicle."""
    service = VehicleService(session)
    vehicle = await service.update(garage.id, vehicle_id, data)
    return APIResponse.ok(data=vehicle.model_dump(mode="json"), message="Vehicle updated")


@router.delete("/{vehicle_id}", response_model=APIResponse)
async def delete_vehicle(vehicle_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Soft-delete a vehicle."""
    service = VehicleService(session)
    await service.delete(garage.id, vehicle_id)
    return APIResponse.ok(message="Vehicle deleted")
