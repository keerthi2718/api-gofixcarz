"""Read the owner's live catalogue without exposing owner/private records.

Distance uses a clamped haversine on a mean-radius Earth (6371.0088 km).
It is geographic proximity, never road distance. Search returns all matches.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Double, and_, case, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.garage import Garage
from app.models.service_package import ServicePackage as Service
from app.schemas.customer_discovery import GarageSearch, LocationInput
from app.services.customer_otp_service import fail

EARTH_RADIUS_KM = 6371.0088


def active_services():
    return and_(Service.deleted_at.is_(None), Service.is_active.is_(True))


def eligible_service():
    return Service.price >= 0


def distance_expression(location: LocationInput):
    if location.latitude is None:
        return cast(literal(None), Double)
    lat, lng = cast(Garage.latitude, Double), cast(Garage.longitude, Double)
    valid = and_(lat.between(-90, 90), lng.between(-180, 180))
    haversine = (
        func.power(func.sin(func.radians(lat - location.latitude) / 2), 2)
        + func.cos(func.radians(location.latitude)) * func.cos(func.radians(lat))
        * func.power(func.sin(func.radians(lng - location.longitude) / 2), 2)
    )
    return case((valid, 2 * EARTH_RADIUS_KM * func.asin(
        func.sqrt(func.least(1.0, func.greatest(0.0, haversine)))
    )), else_=None)


class CustomerDiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def service_row(service):
        eligible = service.price >= 0
        return {
            "id": service.id, "name": service.name, "description": service.description,
            "price_inr": service.price, "currency": "INR",
            "amount": int((Decimal(service.price) * 100).quantize(Decimal("1"))),
            "duration_minutes": service.duration_minutes, "booking_eligible": eligible,
            "unavailable_reason": None if eligible else "SERVICE_CONFIGURATION_INCOMPLETE",
        }

    @staticmethod
    def base_query(location, q="", search_by="all"):
        # contains(autoescape=True) treats %, _ and / as literal search characters.
        garage_match = Garage.name.icontains(q, autoescape=True) if q else literal(False)
        service_match = Service.name.icontains(q, autoescape=True) if q else literal(False)
        counts = select(
            Service.garage_id.label("garage_id"),
            func.count().label("active_count"),
            func.count().filter(service_match).label("matching_count"),
            func.count().filter(eligible_service()).label("bookable_count"),
        ).where(active_services()).group_by(Service.garage_id).subquery()
        query = select(
            Garage, distance_expression(location).label("distance"),
            garage_match.label("garage_match"),
            func.coalesce(counts.c.active_count, 0).label("active_count"),
            func.coalesce(counts.c.matching_count, 0).label("matching_count"),
            func.coalesce(counts.c.bookable_count, 0).label("bookable_count"),
        ).outerjoin(counts, counts.c.garage_id == Garage.id).where(
            Garage.deleted_at.is_(None), Garage.operational_status == "ACTIVE",
            Garage.verification_status == "VERIFIED",
        )
        if q:
            service_found = func.coalesce(counts.c.matching_count, 0) > 0
            query = query.where(
                garage_match if search_by == "garage" else service_found if search_by == "service"
                else or_(garage_match, service_found)
            )
        return query

    async def render(self, rows, q="", search_by="all"):
        if not rows:
            return []
        # One catalogue query for all matching garages, without a preview cap.
        full_ids = [r.Garage.id for r in rows if not q or (r.garage_match and search_by != "service")]
        ids = [r.Garage.id for r in rows]
        previews = (await self.db.execute(select(Service).where(
            active_services(), Service.garage_id.in_(ids),
            or_(Service.garage_id.in_(full_ids), Service.name.icontains(q, autoescape=True)),
        ).order_by(Service.garage_id, func.lower(Service.name), Service.id))).scalars()
        grouped = {identifier: [] for identifier in ids}
        for service in previews:
            grouped[service.garage_id].append(self.service_row(service))
        results = []
        for row in rows:
            g = row.Garage
            results.append({
                **{key: getattr(g, key) for key in ("id", "name", "address", "city", "state", "zipcode", "country")},
                "distance_km": round(row.distance, 3) if row.distance is not None else None,
                "distance_type": "STRAIGHT_LINE",
                "matched_by": (["garage"] if q and row.garage_match and search_by != "service" else [])
                              + (["service"] if q and row.matching_count and search_by != "garage" else []),
                "active_service_count": row.active_count, "matching_service_count": row.matching_count,
                "services": grouped[g.id], "services_has_more": False,
                "services_path": f"/api/v1/customer-app/garages/{g.id}/services",
                "booking_eligible": row.bookable_count > 0,
                "booking_prerequisites": ["SELECT_VEHICLE", "SELECT_SERVICES", "SELECT_DATE"]
                    if row.bookable_count else ["ACTIVE_SERVICE_REQUIRED"],
            })
        return results

    async def search(self, data: GarageSearch):
        query = self.base_query(data, data.q, data.search_by)
        if data.city:
            query = query.where(func.lower(func.trim(Garage.city)) == data.city.lower())
        radius = data.radius_km if data.radius_km is not None else 200.0
        if radius is not None:
            query = query.where(distance_expression(data) <= radius)
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        ordering = [func.lower(Garage.name), Garage.id]
        if data.latitude is not None:
            ordering.insert(0, distance_expression(data).asc().nulls_last())
        rows = (await self.db.execute(query.order_by(*ordering))).all()
        return {"items": await self.render(rows, data.q, data.search_by), "total": total,
                "page": 1, "page_size": total, "pages": 1 if total else 0, "radius_km": radius}

    async def detail(self, garage_id: UUID, location: LocationInput):
        rows = (await self.db.execute(self.base_query(location).where(Garage.id == garage_id))).all()
        if not rows:
            fail("GARAGE_NOT_FOUND", 404)
        return (await self.render(rows))[0]

    async def services(self, garage_id: UUID, page: int, page_size: int | None, q: str):
        exists = await self.db.scalar(select(Garage.id).where(
            Garage.id == garage_id, Garage.deleted_at.is_(None), Garage.operational_status == "ACTIVE",
            Garage.verification_status == "VERIFIED"))
        if not exists:
            fail("GARAGE_NOT_FOUND", 404)
        query = select(Service).where(Service.garage_id == garage_id, active_services())
        if q:
            query = query.where(Service.name.icontains(q, autoescape=True))
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        query = query.order_by(func.lower(Service.name), Service.id)
        if page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(query)).scalars()
        effective_size = page_size if page_size is not None else total
        if page_size is None:
            page = 1
        return {"items": [self.service_row(s) for s in rows], "total": total, "page": page,
                "page_size": effective_size, "pages": (total + effective_size - 1) // effective_size if effective_size else 0}
