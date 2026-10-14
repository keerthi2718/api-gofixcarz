"""Supporting owner/admin writes required by customer read-only journeys.

These routes are intentionally excluded from the customer-only document.
"""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Query
from sqlalchemy import select
from app.api.v1.customer_app import DB
from app.dependencies.garage import CurrentGarage
from app.dependencies.auth import CurrentAdmin
from app.core.admin_policy import require_permission, scope_ids
from app.core.admin_privacy import AdminPrivacyRoute
from app.core.customer_security import now
from app.models.customer_workspace import AppointmentSlot, CustomerBookingLink, CustomerResource
from app.models.job import Job
from app.models.admin_operations import SourceRecord
from app.schemas.customer_workspace import (
    SlotCreate, PublishedJob, InvoicePublish, MessageSend, TicketReply, Moderation, TicketStatusPatch,
)
from app.schemas.response import APIResponse
from app.services.customer_activity_service import CustomerActivityService
from app.services.customer_otp_service import fail
from app.services.admin_operations_service import AdminOperationsService

router = APIRouter(tags=["Customer workflow participants"])
admin_router = APIRouter(route_class=AdminPrivacyRoute)


async def owned_job(db, garage, identifier):
    job = (await db.execute(select(Job).where(
        Job.id == identifier, Job.garage_id == garage.id, Job.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not job:
        fail("RESOURCE_NOT_FOUND", 404)
    link = await db.get(CustomerBookingLink, job.booking_id) if job.booking_id else None
    if not link:
        fail("CUSTOMER_APP_LINK_REQUIRED", 409)
    svc = CustomerActivityService(db, link.customer_id)
    await svc.lock("account", link.customer_id)
    await db.execute(select(Job.id).where(Job.id == identifier).with_for_update())
    await db.refresh(job)
    return job, link


@router.post("/garage/customer-slots", response_model=APIResponse[dict], status_code=201)
async def slot_create(data: SlotCreate, garage: CurrentGarage, db: DB):
    svc = CustomerActivityService(db, None)
    await svc.lock("garage-slots", garage.id)
    if garage.operational_status != "ACTIVE":
        fail("GARAGE_UNAVAILABLE", 409)
    existing = (await db.execute(select(AppointmentSlot).where(
        AppointmentSlot.garage_id == garage.id, AppointmentSlot.active.is_(True)))).scalars().all()
    if any(row.timezone != data.timezone for row in existing):
        fail("GARAGE_TIMEZONE_CONFLICT", 409)
    if any(row.starts_at < data.ends_at and row.ends_at > data.starts_at for row in existing):
        fail("SLOT_OVERLAP", 409)
    row = AppointmentSlot(garage_id=garage.id, **data.model_dump())
    db.add(row)
    await db.flush()
    return APIResponse.ok({"id": row.id, **data.model_dump(), "active": True}, status_code=201)


@router.get("/garage/customer-slots", response_model=APIResponse[dict])
async def slots(garage: CurrentGarage, db: DB, date: str | None = None):
    rows = (await db.execute(select(AppointmentSlot).where(
        AppointmentSlot.garage_id == garage.id).order_by(AppointmentSlot.starts_at))).scalars().all()
    return APIResponse.ok({"items": [{
        name: getattr(row, name) for name in ("id", "starts_at", "ends_at", "timezone", "capacity", "active")
    } for row in rows]})


@router.delete("/garage/customer-slots/{slot_id}", response_model=APIResponse[dict])
async def slot_disable(slot_id: UUID, garage: CurrentGarage, db: DB):
    row = (await db.execute(select(AppointmentSlot).where(
        AppointmentSlot.id == slot_id, AppointmentSlot.garage_id == garage.id
    ).with_for_update())).scalar_one_or_none()
    if not row:
        fail("RESOURCE_NOT_FOUND", 404)
    row.active = False  # Existing bookings stay accessible.
    return APIResponse.ok({"id": row.id, "active": False})


@router.put("/jobs/{job_id}/customer-publication", response_model=APIResponse[dict])
async def publish_job(job_id: UUID, data: PublishedJob, garage: CurrentGarage, db: DB):
    job, link = await owned_job(db, garage, job_id)
    from app.utils.s3 import is_garage_object_key
    if len(set(data.photo_keys)) != len(data.photo_keys) or any(
        not is_garage_object_key(key, garage.id) or key not in (job.photos or [])
        for key in data.photo_keys
    ):
        fail("JOB_PHOTO_INVALID", 422)
    svc = CustomerActivityService(db, link.customer_id)
    await svc.lock("account", link.customer_id)
    row = (await db.execute(svc.query("JOB_PUBLICATION").where(
        CustomerResource.dedupe_key == str(job.id)))).scalar_one_or_none()
    if row:
        row.payload = data.model_dump()
    else:
        row = await svc.add("JOB_PUBLICATION", data.model_dump(), garage_id=garage.id, key=str(job.id))
    await svc.notify("JOBS", "Garage published a job update", job.id, f"job-publication:{row.id}:{now().isoformat()}")
    return APIResponse.ok(await svc.job_row(job))


@router.post("/jobs/{job_id}/customer-invoice", response_model=APIResponse[dict], status_code=201)
async def publish_invoice(job_id: UUID, data: InvoicePublish, garage: CurrentGarage, db: DB):
    job, link = await owned_job(db, garage, job_id)
    if job.status.value != "COMPLETED":
        fail("JOB_NOT_COMPLETED", 409)
    svc = CustomerActivityService(db, link.customer_id)
    await svc.lock("account", link.customer_id)
    existing = (await db.execute(select(SourceRecord).where(
        SourceRecord.kind == "INVOICE", SourceRecord.job_id == job.id,
        SourceRecord.customer_id == link.customer_id))).scalar_one_or_none()
    if existing:
        fail("INVOICE_ALREADY_PUBLISHED", 409)
    total = data.subtotal + data.tax_amount - data.discount_amount
    from uuid import uuid4
    row = SourceRecord(id=uuid4(), kind="INVOICE", source="customer-workflow-owner-api",
                       external_id=f"invoice:{job.id}", garage_id=garage.id, customer_id=link.customer_id,
                       booking_id=job.booking_id, job_id=job.id, status="ISSUED", occurred_at=now(),
                       amount=total, currency="INR", payload=data.model_dump())
    db.add(row)
    await db.flush()
    await svc.notify("INVOICES", "Invoice published", row.id, f"invoice:{row.id}")
    return APIResponse.ok(await svc.invoice_row(row), status_code=201)


async def owner_conversation(db, garage, identifier):
    row = (await db.execute(select(CustomerResource).where(
        CustomerResource.id == identifier, CustomerResource.kind == "CONVERSATION",
        CustomerResource.garage_id == garage.id))).scalar_one_or_none()
    if not row:
        fail("RESOURCE_NOT_FOUND", 404)
    svc = CustomerActivityService(db, row.customer_id)
    await svc.lock("account", row.customer_id)
    return svc, row


@router.get("/garage/customer-conversations", response_model=APIResponse[dict])
async def owner_conversations(garage: CurrentGarage, db: DB,
                              page: Annotated[int, Query(ge=1)] = 1,
                              page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    svc = CustomerActivityService(db, None)
    return APIResponse.ok(await svc.page(select(CustomerResource).where(
        CustomerResource.kind == "CONVERSATION", CustomerResource.garage_id == garage.id
    ).order_by(CustomerResource.created_at.desc(), CustomerResource.id), page, page_size))


@router.get("/garage/customer-conversations/{conversation_id}/messages", response_model=APIResponse[dict])
async def owner_messages(conversation_id: UUID, garage: CurrentGarage, db: DB,
                         cursor: UUID | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    svc, row = await owner_conversation(db, garage, conversation_id)
    return APIResponse.ok(await svc.cursor_messages(row, "MESSAGE", cursor, limit))


@router.post("/garage/customer-conversations/{conversation_id}/messages", response_model=APIResponse[dict])
async def owner_reply(conversation_id: UUID, data: MessageSend, garage: CurrentGarage, db: DB):
    svc, row = await owner_conversation(db, garage, conversation_id)
    result, created = await svc.conversation_send(conversation_id, data, sender_role="GARAGE", sender_id=garage.user_id)
    return APIResponse.ok(result)


def admin_query(db, kind, permission):
    require_permission(db, permission)
    query = select(CustomerResource).where(CustomerResource.kind == kind)
    scopes = scope_ids(db)
    if scopes is not None:
        query = query.where(CustomerResource.garage_id.in_(scopes))
    return query


async def admin_resource(db, identifier, kind, permission):
    row = (await db.execute(admin_query(db, kind, permission).where(
        CustomerResource.id == identifier))).scalar_one_or_none()
    if not row:
        fail("RESOURCE_NOT_FOUND", 404)
    svc = CustomerActivityService(db, row.customer_id)
    await svc.lock("account", row.customer_id)
    await AdminOperationsService(db).audit("customer-workflow." + kind.lower(), identifier)
    return svc, row


@admin_router.get("/admin/customer-support/tickets", response_model=APIResponse[dict])
async def admin_tickets(admin: CurrentAdmin, db: DB,
                        page: Annotated[int, Query(ge=1)] = 1,
                        page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    query = admin_query(db, "TICKET", "support.read")
    await AdminOperationsService(db).audit("customer-workflow.support.list")
    return APIResponse.ok(await CustomerActivityService(db, None).page(
        query.order_by(CustomerResource.created_at.desc(), CustomerResource.id), page, page_size))


@admin_router.get("/admin/customer-support/tickets/{ticket_id}/messages", response_model=APIResponse[dict])
async def admin_ticket_messages(ticket_id: UUID, admin: CurrentAdmin, db: DB,
                                cursor: UUID | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    svc, row = await admin_resource(db, ticket_id, "TICKET", "support.read")
    return APIResponse.ok(await svc.cursor_messages(row, "TICKET_MESSAGE", cursor, limit))


@admin_router.post("/admin/customer-support/tickets/{ticket_id}/messages", response_model=APIResponse[dict])
async def admin_ticket_reply(ticket_id: UUID, data: TicketReply, admin: CurrentAdmin, db: DB):
    svc, row = await admin_resource(db, ticket_id, "TICKET", "support.reply")
    if data.attachment_ids:
        fail("ADMIN_REPLY_ATTACHMENTS_UNSUPPORTED", 422)
    result, created = await svc.ticket_send(ticket_id, data, sender_role="ADMIN", sender_id=admin.id)
    return APIResponse.ok(result)


@admin_router.patch("/admin/customer-support/tickets/{ticket_id}", response_model=APIResponse[dict])
async def admin_ticket_status(ticket_id: UUID, data: TicketStatusPatch, admin: CurrentAdmin, db: DB):
    svc, row = await admin_resource(db, ticket_id, "TICKET", "support.manage")
    row.status = data.status
    await svc.notify("SUPPORT", "Support ticket status updated", row.id, f"ticket-status:{row.id}:{now().isoformat()}")
    return APIResponse.ok(svc.row(row))


@admin_router.get("/admin/customer-reviews", response_model=APIResponse[dict])
async def admin_reviews(admin: CurrentAdmin, db: DB,
                        page: Annotated[int, Query(ge=1)] = 1,
                        page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    query = admin_query(db, "REVIEW", "reviews.read")
    await AdminOperationsService(db).audit("customer-workflow.review.list")
    return APIResponse.ok(await CustomerActivityService(db, None).page(
        query.order_by(CustomerResource.created_at.desc(), CustomerResource.id), page, page_size))


@admin_router.patch("/admin/customer-reviews/{review_id}", response_model=APIResponse[dict])
async def admin_review_moderate(review_id: UUID, data: Moderation, admin: CurrentAdmin, db: DB):
    svc, row = await admin_resource(db, review_id, "REVIEW", "reviews.moderate")
    row.status = data.status
    await svc.notify("REVIEWS", "Review moderation updated", row.id, f"review-status:{row.id}:{now().isoformat()}")
    return APIResponse.ok(svc.row(row))


router.include_router(admin_router)
