import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.service_package_repository import ServicePackageRepository
from app.schemas.response import PaginatedData
from app.schemas.service_package import (
    ServicePackageCreate,
    ServicePackageResponse,
    ServicePackageUpdate,
)


class ServicePackageService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ServicePackageRepository(session)

    async def create(self, garage_id: uuid.UUID, data: ServicePackageCreate) -> ServicePackageResponse:
        pkg = await self.repo.create(garage_id, data)
        return ServicePackageResponse.model_validate(pkg)

    async def list(
        self,
        garage_id: uuid.UUID,
        search: Optional[str] = None,
        active_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedData[ServicePackageResponse]:
        page_size = min(page_size, 100)
        items, total = await self.repo.list(
            garage_id, search=search, active_only=active_only, page=page, page_size=page_size
        )
        return PaginatedData(
            items=[ServicePackageResponse.model_validate(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    async def get(self, garage_id: uuid.UUID, pkg_id: uuid.UUID) -> ServicePackageResponse:
        pkg = await self.repo.get_by_id(pkg_id, garage_id)
        if not pkg:
            raise NotFoundException("Service package not found")
        return ServicePackageResponse.model_validate(pkg)

    async def update(
        self, garage_id: uuid.UUID, pkg_id: uuid.UUID, data: ServicePackageUpdate
    ) -> ServicePackageResponse:
        pkg = await self.repo.get_by_id(pkg_id, garage_id)
        if not pkg:
            raise NotFoundException("Service package not found")
        updated = await self.repo.update(pkg, data)
        return ServicePackageResponse.model_validate(updated)

    async def delete(self, garage_id: uuid.UUID, pkg_id: uuid.UUID) -> None:
        pkg = await self.repo.get_by_id(pkg_id, garage_id)
        if not pkg:
            raise NotFoundException("Service package not found")
        await self.repo.delete(pkg)
