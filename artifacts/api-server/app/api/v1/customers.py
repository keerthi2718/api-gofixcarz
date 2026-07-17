import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from app.schemas.response import APIResponse, PaginatedData
from app.services.customer_service import CustomerService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=APIResponse[CustomerResponse], status_code=status.HTTP_201_CREATED)
async def create_customer(data: CustomerCreate, garage: CurrentGarage, session: DBSession):
    """Create a new customer for the current garage."""
    service = CustomerService(session)
    customer = await service.create(garage.id, data)
    return JSONResponse(
        status_code=201,
        content=APIResponse.created(
            data=customer.model_dump(mode="json"),
            message="Customer created successfully",
        ).model_dump(),
    )


@router.get("", response_model=APIResponse[PaginatedData[CustomerResponse]])
async def list_customers(
    garage: CurrentGarage,
    session: DBSession,
    search: Optional[str] = Query(None, description="Search by name or mobile"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all customers for the current garage (paginated)."""
    service = CustomerService(session)
    result = await service.list(garage.id, search=search, page=page, page_size=page_size)
    return APIResponse.ok(data=result.model_dump(mode="json"), message="Customers retrieved")


@router.get("/{customer_id}", response_model=APIResponse[CustomerResponse])
async def get_customer(customer_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Get a single customer by ID."""
    service = CustomerService(session)
    customer = await service.get(garage.id, customer_id)
    return APIResponse.ok(data=customer.model_dump(mode="json"), message="Customer retrieved")


@router.put("/{customer_id}", response_model=APIResponse[CustomerResponse])
async def update_customer(
    customer_id: uuid.UUID, data: CustomerUpdate, garage: CurrentGarage, session: DBSession
):
    """Update a customer."""
    service = CustomerService(session)
    customer = await service.update(garage.id, customer_id, data)
    return APIResponse.ok(data=customer.model_dump(mode="json"), message="Customer updated")


@router.delete("/{customer_id}", response_model=APIResponse)
async def delete_customer(customer_id: uuid.UUID, garage: CurrentGarage, session: DBSession):
    """Soft-delete a customer."""
    service = CustomerService(session)
    await service.delete(garage.id, customer_id)
    return APIResponse.ok(message="Customer deleted")
