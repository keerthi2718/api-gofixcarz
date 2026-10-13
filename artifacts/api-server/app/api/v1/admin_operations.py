import uuid
from datetime import datetime
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from app.api.v1.admin import DBSession, Page, PageSize
from app.api.v1.admin_monitoring import Filters
from app.core.admin_privacy import AdminPrivacyRoute
from app.core.admin_policy import require_permission
from app.core.admin_read_filters import reject_unknown_admin_query
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.models.admin_operations import CustomerAccount, SourceRecord, AdminResource, SupportMessage
from app.models.notification import Notification
from app.schemas.admin_operations import (
    Assignment, Priority, TicketStatus, Reply, GarageStatus, GarageVerification, AnnouncementPreview, AnnouncementSend,
)
from app.schemas.response import APIResponse
from app.services.admin_operations_service import (
    AdminOperationsService, record_row, message_row, announcement_row, now,
)

router = APIRouter(route_class=AdminPrivacyRoute, dependencies=[
    Depends(get_current_admin), Depends(reject_unknown_admin_query)])
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


@router.patch("/garages/{garage_id}/status", response_model=APIResponse)
async def garage_status(garage_id: uuid.UUID, data: GarageStatus, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminOperationsService(session).mutate_garage(garage_id, data))


@router.patch("/garages/{garage_id}/verification", response_model=APIResponse)
async def garage_verification(garage_id: uuid.UUID, data: GarageVerification, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminOperationsService(session).mutate_garage(garage_id, data, True))


@router.get("/garages/{garage_id}/reviews", response_model=APIResponse)
async def garage_reviews(garage_id: uuid.UUID, admin: CurrentAdmin, session: DBSession,
                         moderation_status: Literal["PENDING", "PUBLISHED", "HIDDEN"] | None = None,
                         page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    if not await service.admin.repo.get_garage(garage_id):
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    query = service.records_query("REVIEW", status=moderation_status).where(SourceRecord.garage_id == garage_id)
    result = await service.paged(query, page, page_size)
    await service.audit("garage.reviews", garage_id)
    return APIResponse.ok(data=result)


@router.get("/customers", response_model=APIResponse)
async def customers(admin: CurrentAdmin, session: DBSession, page: Page = 1, page_size: PageSize = 20,
                    account_status: Literal["ACTIVE", "INACTIVE", "BLOCKED", "DELETED"] | None = None,
                    has_failed_payments: bool | None = None, has_support_flags: bool | None = None,
                    inactive_since: datetime | None = None, search: str | None = Query(None, max_length=200)):
    service = AdminOperationsService(session)
    query = select(CustomerAccount)
    if account_status:
        query = query.where(CustomerAccount.account_status == account_status)
    if search:
        query = query.where(or_(CustomerAccount.name.ilike(f"%{search}%"), CustomerAccount.email.ilike(f"%{search}%")))
    if inactive_since:
        if not inactive_since.tzinfo:
            raise HTTPException(422, "inactive_since requires timezone")
        query = query.where(or_(CustomerAccount.last_activity_at.is_(None), CustomerAccount.last_activity_at < inactive_since))
    for flag, kind in ((has_failed_payments, "PAYMENT"), (has_support_flags, "TICKET")):
        if flag is not None:
            if kind == "PAYMENT":
                require_permission(session, "finance.read")
            exists = select(SourceRecord.id).where(
                SourceRecord.customer_id == CustomerAccount.id, SourceRecord.kind == kind,
                SourceRecord.status == "FAILED" if kind == "PAYMENT" else SourceRecord.status.notin_(["CLOSED", "RESOLVED"]),
            ).exists()
            query = query.where(exists if flag else ~exists)
    rows, total = await service.admin.repo.page(query.order_by(CustomerAccount.created_at.desc(), CustomerAccount.id), page, page_size)
    result = {"items": [await service.customer_row(row) for row in rows], "total": total, "page": page, "page_size": page_size}
    await service.audit("customers.list")
    return APIResponse.ok(data=result)


@router.get("/customers/{customer_id}", response_model=APIResponse)
async def customer_detail(customer_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminOperationsService(session)
    result = await service.customer_row(await service.customer(customer_id))
    result["vehicles"] = (await service.paged(service.records_query("VEHICLE", customer_id=customer_id)))["items"]
    result["reviews"] = (await service.paged(service.records_query("REVIEW", customer_id=customer_id)))["items"]
    result["preview_limit"] = 20
    await service.audit("customers.read", customer_id)
    return APIResponse.ok(data=result)


@router.get("/customers/{customer_id}/vehicles", response_model=APIResponse)
async def customer_vehicles(customer_id: uuid.UUID, admin: CurrentAdmin, session: DBSession,
                            page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    await service.customer(customer_id)
    result = await service.paged(service.records_query("VEHICLE", customer_id=customer_id), page, page_size)
    await service.audit("customers.vehicles", customer_id)
    return APIResponse.ok(data=result)


@router.get("/customers/{customer_id}/reviews", response_model=APIResponse)
async def customer_reviews(customer_id: uuid.UUID, admin: CurrentAdmin, session: DBSession,
                           page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    await service.customer(customer_id)
    result = await service.paged(service.records_query("REVIEW", customer_id=customer_id), page, page_size)
    await service.audit("customers.reviews", customer_id)
    return APIResponse.ok(data=result)


@router.get("/jobs/delays", response_model=APIResponse)
async def delays(admin: CurrentAdmin, session: DBSession, filters: Filters,
                 status: Literal["OPEN", "IN_PROGRESS", "WAITING_FOR_PARTS", "QUALITY_CHECK", "READY"] | None = None,
                 overdue: bool | None = None, page: Page = 1, page_size: PageSize = 20):
    from app.models.job import JobStatus
    service = AdminOperationsService(session)
    items, stamp = await service.delays(filters, JobStatus(status) if status else None, overdue)
    await service.audit("jobs.delays")
    return APIResponse.ok(data={"items": items[(page-1)*page_size:page*page_size], "total": len(items),
                               "page": page, "page_size": page_size, "as_of": stamp})


@router.get("/alerts", response_model=APIResponse)
async def alerts(admin: CurrentAdmin, session: DBSession, filters: Filters,
                 type: Literal["JOB_DELAY"] = "JOB_DELAY", severity: Literal["MEDIUM", "HIGH"] | None = None,
                 page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    items, stamp = await service.delays(filters, overdue=True)
    for item in items:
        item.update(type="JOB_DELAY", severity="HIGH" if item["state_age_hours"] >= 2*item["threshold_hours"] else "MEDIUM",
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{item['job_id']}:{item['status']}:{item['state_entered_at']}")))
    if severity:
        items = [item for item in items if item["severity"] == severity]
    await service.audit("alerts.list")
    return APIResponse.ok(data={"items": items[(page-1)*page_size:page*page_size], "total": len(items),
                               "page": page, "page_size": page_size, "as_of": stamp, "generation": "live deterministic state episodes"})


@router.get("/notifications", response_model=APIResponse)
async def notifications(admin: CurrentAdmin, session: DBSession,
                        garage_id: uuid.UUID | None = None, channel: Literal["IN_APP", "PUSH", "SMS", "EMAIL"] | None = None,
                        status: str | None = Query(None, max_length=40), page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    if channel in ("PUSH", "SMS", "EMAIL"):
        query = service.records_query("DELIVERY", status=status).where(SourceRecord.payload["channel"].astext == channel)
        if garage_id:
            query = query.where(SourceRecord.garage_id == garage_id)
        result = await service.paged(query, page, page_size)
    else:
        query = select(Notification)
        if garage_id:
            query = query.where(Notification.garage_id == garage_id)
        if status not in (None, "DELIVERED", "READ"):
            query = query.where(False)
        elif status == "READ":
            query = query.where(Notification.read_at.is_not(None))
        result = await service.paged(query.order_by(Notification.created_at.desc(), Notification.id), page, page_size,
                                     lambda n: {"id": n.id, "garage_id": n.garage_id, "title": n.title,
                                                "message": n.message, "channel": "IN_APP",
                                                "status": "READ" if n.read_at else "DELIVERED", "read_at": n.read_at})
    await service.audit("notifications.list")
    return APIResponse.ok(data=result)


@router.get("/notifications/{notification_id}", response_model=APIResponse)
async def notification_detail(notification_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminOperationsService(session)
    notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
    if notification:
        result = {"id": notification.id, "garage_id": notification.garage_id, "title": notification.title,
                  "message": notification.message, "channel": "IN_APP", "created_at": notification.created_at,
                  "status": "READ" if notification.read_at else "DELIVERED", "attempts": []}
    else:
        result = record_row(await service.record(notification_id, "DELIVERY"))
    await service.audit("notifications.read", notification_id)
    return APIResponse.ok(data=result)


@router.post("/announcements/preview", response_model=APIResponse)
async def preview_announcement(data: AnnouncementPreview, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminOperationsService(session).preview(data))


@router.post("/announcements", response_model=APIResponse, status_code=202)
async def send_announcement(data: AnnouncementSend, admin: CurrentAdmin, session: DBSession, idempotency_key: Key):
    return APIResponse.ok(data=await AdminOperationsService(session).send(data, idempotency_key), status_code=202)


@router.get("/announcements", response_model=APIResponse)
async def announcements(admin: CurrentAdmin, session: DBSession, page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    query = select(AdminResource).where(AdminResource.kind == "ANNOUNCEMENT", AdminResource.actor_id == admin.id)
    result = await service.paged(query.order_by(AdminResource.created_at.desc(), AdminResource.id), page, page_size, announcement_row)
    await service.audit("announcements.list")
    return APIResponse.ok(data=result)


@router.get("/announcements/{announcement_id}", response_model=APIResponse)
async def announcement_detail(announcement_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminOperationsService(session)
    result = announcement_row(await service.resource(announcement_id, "ANNOUNCEMENT"))
    await service.audit("announcements.read", announcement_id)
    return APIResponse.ok(data=result)


@router.get("/announcements/{announcement_id}/deliveries", response_model=APIResponse)
async def announcement_deliveries(announcement_id: uuid.UUID, admin: CurrentAdmin, session: DBSession,
                                  status: Literal["DELIVERED", "FAILED", "QUEUED"] | None = None,
                                  page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    resource = await service.resource(announcement_id, "ANNOUNCEMENT")
    items = resource.payload["deliveries"]
    if status:
        items = [item for item in items if item["status"] == status]
    await service.audit("announcements.deliveries", announcement_id)
    return APIResponse.ok(data={"items": items[(page-1)*page_size:page*page_size], "total": len(items),
                               "page": page, "page_size": page_size})


@router.get("/support/tickets", response_model=APIResponse)
async def tickets(admin: CurrentAdmin, session: DBSession, filters: Filters,
                  customer_id: uuid.UUID | None = None, status: str | None = Query(None, max_length=40),
                  priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] | None = None,
                  page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    query = service.records_query("TICKET", filters, status, customer_id)
    if priority:
        query = query.where(func.coalesce(SourceRecord.payload["priority"].astext, "NORMAL") == priority)
    result = await service.paged(query, page, page_size)
    await service.audit("support.list")
    return APIResponse.ok(data=result)


@router.get("/support/tickets/{ticket_id}", response_model=APIResponse)
async def ticket_detail(ticket_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminOperationsService(session)
    result = record_row(await service.record(ticket_id, "TICKET"))
    await service.audit("support.read", ticket_id)
    return APIResponse.ok(data=result)


@router.patch("/support/tickets/{ticket_id}/assignment", response_model=APIResponse)
async def ticket_assignment(ticket_id: uuid.UUID, data: Assignment, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminOperationsService(session).ticket_change(ticket_id, data, "assignment"))


@router.patch("/support/tickets/{ticket_id}/priority", response_model=APIResponse)
async def ticket_priority(ticket_id: uuid.UUID, data: Priority, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminOperationsService(session).ticket_change(ticket_id, data, "priority"))


@router.patch("/support/tickets/{ticket_id}/status", response_model=APIResponse)
async def ticket_status(ticket_id: uuid.UUID, data: TicketStatus, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminOperationsService(session).ticket_change(ticket_id, data, "status"))


@router.get("/support/tickets/{ticket_id}/messages", response_model=APIResponse)
async def ticket_messages(ticket_id: uuid.UUID, admin: CurrentAdmin, session: DBSession,
                          limit: int = Query(30, ge=1, le=100), cursor: uuid.UUID | None = None):
    service = AdminOperationsService(session)
    await service.record(ticket_id, "TICKET")
    query = select(SupportMessage).where(SupportMessage.ticket_id == ticket_id)
    if cursor:
        previous = (await session.execute(query.where(SupportMessage.id == cursor))).scalar_one_or_none()
        if not previous:
            raise HTTPException(422, "CURSOR_INVALID")
        query = query.where(or_(SupportMessage.created_at > previous.created_at,
                               (SupportMessage.created_at == previous.created_at) & (SupportMessage.id > previous.id)))
    rows = (await session.execute(query.order_by(SupportMessage.created_at, SupportMessage.id).limit(limit+1))).scalars().all()
    await service.audit("support.messages", ticket_id)
    return APIResponse.ok(data={"items": [message_row(row) for row in rows[:limit]],
                               "next_cursor": rows[limit-1].id if len(rows) > limit else None})


@router.post("/support/tickets/{ticket_id}/messages", response_model=APIResponse, status_code=201)
async def ticket_reply(ticket_id: uuid.UUID, data: Reply, admin: CurrentAdmin, session: DBSession):
    return APIResponse.created(data=await AdminOperationsService(session).reply(ticket_id, data))
