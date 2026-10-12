"""Explicit, timezone-aware windows for admin reads; no new metric policy."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import UUID

from fastapi import HTTPException, Request
from app.core.exceptions import BadRequestException


@dataclass(frozen=True)
class AdminReadFilters:
    date_from: date | None = None
    date_to: date | None = None
    timezone: str = "UTC"
    city: str | None = None
    garage_id: UUID | None = None
    owner_id: UUID | None = None

    def __post_init__(self):
        if self.city is not None:
            object.__setattr__(self, "city", self.city.strip())
            if not self.city:
                raise HTTPException(422, "city cannot be blank")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "Invalid IANA timezone") from None
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                # Preserve the existing admin date-order failure contract.
                raise BadRequestException("date_from must be before or equal to date_to")
            if (self.date_to - self.date_from).days > 366:
                raise HTTPException(422, "Date range cannot exceed 366 days")
        if self.date_to == date.max:
            raise HTTPException(422, "date_to is outside the supported range")

    def boundary(self, day: date, *, exclusive_end=False):
        if exclusive_end:
            day += timedelta(days=1)
        try:
            return datetime.combine(day, time.min, ZoneInfo(self.timezone)).astimezone(timezone.utc)
        except (OverflowError, ValueError):
            raise HTTPException(422, "Date is outside the supported timezone range") from None

    def metadata(self):
        return {
            "date_from": self.date_from, "date_to": self.date_to,
            "timezone": self.timezone, "city": self.city,
            "garage_id": self.garage_id, "owner_id": self.owner_id,
        }


def apply_admin_filters(query, filters, timestamp=None):
    """Query must already join/select Garage. Inventory is not date-cohorted."""
    if filters is None:
        return query
    from app.models.garage import Garage
    if filters.city is not None:
        query = query.where(Garage.city.ilike(filters.city.strip().replace("%", r"\%").replace("_", r"\_")))
    if filters.garage_id is not None:
        query = query.where(Garage.id == filters.garage_id)
    if filters.owner_id is not None:
        query = query.where(Garage.user_id == filters.owner_id)
    if timestamp is not None:
        if filters.date_from:
            query = query.where(timestamp >= filters.boundary(filters.date_from))
        if filters.date_to:
            query = query.where(timestamp < filters.boundary(filters.date_to, exclusive_end=True))
    return query


async def reject_unknown_admin_query(request: Request):
    """Fail rather than silently ignore draft filters that are not implemented."""
    route = request.scope.get("route")
    if not route or not hasattr(route, "dependant"):
        return
    allowed = set()

    def collect(dependant):
        allowed.update(field.alias for field in dependant.query_params)
        for dependency in dependant.dependencies:
            collect(dependency)

    collect(route.dependant)
    unknown = sorted(set(request.query_params) - allowed)
    if unknown:
        raise HTTPException(422, f"Unsupported query parameters: {', '.join(unknown)}")
