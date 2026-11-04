"""Authenticated customer discovery; no customer location in URL/access logs."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.v1.customer_app import DB, Principal
from app.schemas.customer_discovery import (
    DiscoveryGarage, DiscoveryService, GarageSearch, GarageSearchResults, LocationInput,
)
from app.schemas.response import APIResponse, PaginatedData
from app.services.customer_discovery_service import CustomerDiscoveryService

router = APIRouter(prefix="/customer-app/garages", tags=["Customer Discovery"], responses={
    401: {"model": APIResponse, "description": "Customer session required"},
    404: {"model": APIResponse, "description": "Garage not found or unavailable"},
    422: {"model": APIResponse, "description": "Invalid search or location"},
})


@router.post("/search", response_model=APIResponse[GarageSearchResults])
async def search(data: GarageSearch, db: DB, who: Principal, response: Response):
    """Service/garage/city discovery. Nearby-only defaults to 5 km; city browsing has no implicit radius. Explicit radius is strict, maximum 200 km."""
    response.headers["Cache-Control"] = "no-store"
    return APIResponse.ok(await CustomerDiscoveryService(db).search(data))


@router.get("/{garage_id}", response_model=APIResponse[DiscoveryGarage])
async def detail(garage_id: UUID, db: DB, who: Principal, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return APIResponse.ok(await CustomerDiscoveryService(db).detail(garage_id, LocationInput()))


@router.post("/{garage_id}/details", response_model=APIResponse[DiscoveryGarage])
async def located_detail(garage_id: UUID, data: LocationInput, db: DB, who: Principal, response: Response):
    """Selected garage distance, using the same body coordinates as search."""
    response.headers["Cache-Control"] = "no-store"
    return APIResponse.ok(await CustomerDiscoveryService(db).detail(garage_id, data))


@router.get("/{garage_id}/services", response_model=APIResponse[PaginatedData[DiscoveryService]])
async def services(garage_id: UUID, db: DB, who: Principal, response: Response,
                   page: Annotated[int, Query(ge=1, le=100000)] = 1,
                   page_size: Annotated[int, Query(ge=1, le=100)] = 20,
                   q: Annotated[str, Query(max_length=100)] = ""):
    response.headers["Cache-Control"] = "no-store"
    return APIResponse.ok(await CustomerDiscoveryService(db).services(garage_id, page, page_size, q.strip()))
