import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_package import ServicePackage
from app.schemas.service_package import ServicePackageCreate, ServicePackageUpdate


class ServicePackageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, pkg_id: uuid.UUID, garage_id: uuid.UUID
    ) -> Optional[ServicePackage]:
        result = await self.session.execute(
            select(ServicePackage).where(
                ServicePackage.id == pkg_id,
                ServicePackage.garage_id == garage_id,
                ServicePackage.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        garage_id: uuid.UUID,
        search: Optional[str] = None,
        active_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ServicePackage], int]:
        base_q = select(ServicePackage).where(
            ServicePackage.garage_id == garage_id,
            ServicePackage.deleted_at.is_(None),
        )
        if search:
            base_q = base_q.where(ServicePackage.name.ilike(f"%{search}%"))
        if active_only:
            base_q = base_q.where(ServicePackage.is_active.is_(True))

        total: int = (
            await self.session.execute(
                select(func.count()).select_from(base_q.subquery())
            )
        ).scalar_one()

        items_q = (
            base_q.order_by(ServicePackage.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(items_q)).scalars().all()
        return list(rows), total

    async def create(self, garage_id: uuid.UUID, data: ServicePackageCreate) -> ServicePackage:
        pkg = ServicePackage(id=uuid.uuid4(), garage_id=garage_id, **data.model_dump())
        self.session.add(pkg)
        await self.session.flush()
        await self.session.refresh(pkg)
        return pkg

    async def update(self, pkg: ServicePackage, data: ServicePackageUpdate) -> ServicePackage:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(pkg, field, value)
        pkg.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(pkg)
        return pkg

    async def delete(self, pkg: ServicePackage) -> None:
        pkg.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
