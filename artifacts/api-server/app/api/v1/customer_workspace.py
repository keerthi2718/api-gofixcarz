"""Customer-only workflow APIs; all resources are scoped by verified principal."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Header, Path, Query, Response, UploadFile
from sqlalchemy import select
from app.api.v1.customer_app import DB, Principal
from app.models.booking import BookingStatus
from app.models.job import JobStatus
from app.models.customer_workspace import CustomerResource, CustomerVehicle
from app.schemas.customer_workspace import (
    VehicleCreate, VehiclePatch, PhotoSet, QuoteRequest, BookingSubmit, CancelRequest,
    DeviceRequest, Category, NotificationRead, ReadAll, ConversationStart, MessageSend,
    ReadMarker, ReviewCreate, ReviewPatch, TicketCreate, TicketReply,
)
from app.schemas.customer_app import StrictInput
from app.schemas.customer_booking import CustomerBookingResponse, CustomerQuoteResponse
from app.schemas.response import APIResponse
from app.services.customer_activity_service import CustomerActivityService
from app.services.customer_vehicle_service import CustomerVehicleService
from app.services.customer_otp_service import fail

router = APIRouter(prefix="/customer-app", tags=["Customer App"], responses={
    401: {"model": APIResponse, "description": "Customer authentication/session required"},
    404: {"model": APIResponse, "description": "Missing or non-owned resource"},
    409: {"model": APIResponse, "description": "Workflow, capacity, ownership or idempotency conflict"},
    422: {"model": APIResponse, "description": "Invalid request fields"},
    503: {"model": APIResponse, "description": "Required external service unavailable"},
})
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]
Limit = Annotated[int, Query(ge=1, le=100)]
Installation = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,100}$")]


async def workspace(db: DB, who: Principal):
    return CustomerActivityService(db, who[0].id)


Workspace = Annotated[CustomerActivityService, Depends(workspace)]


@router.post("/vehicles", response_model=APIResponse[dict], status_code=201)
async def vehicle_create(data: VehicleCreate, svc: Workspace):
    return APIResponse.ok(await CustomerVehicleService(svc.db, svc.customer_id).create_vehicle(data), status_code=201)


@router.get("/vehicles", response_model=APIResponse[dict])
async def vehicles(svc: Workspace, page: Page = 1, page_size: Size = 20):
    service = CustomerVehicleService(svc.db, svc.customer_id)
    async def render(row):
        return service.vehicle_row(row)
    return APIResponse.ok(await service.page(service.vehicles().order_by(
        CustomerVehicle.created_at, CustomerVehicle.id), page, page_size, render))


@router.get("/vehicles/{vehicle_id}", response_model=APIResponse[dict])
async def vehicle_detail(vehicle_id: UUID, svc: Workspace):
    return APIResponse.ok(CustomerVehicleService.vehicle_row(await svc.vehicle(vehicle_id)))


@router.patch("/vehicles/{vehicle_id}", response_model=APIResponse[dict])
async def vehicle_patch(vehicle_id: UUID, data: VehiclePatch, svc: Workspace):
    return APIResponse.ok(await CustomerVehicleService(svc.db, svc.customer_id).patch_vehicle(vehicle_id, data))


@router.delete("/vehicles/{vehicle_id}", response_model=APIResponse[dict])
async def vehicle_delete(vehicle_id: UUID, svc: Workspace):
    return APIResponse.ok(await CustomerVehicleService(svc.db, svc.customer_id).remove_vehicle(vehicle_id))


@router.put("/vehicles/{vehicle_id}/default", response_model=APIResponse[dict])
async def default_vehicle(vehicle_id: UUID, svc: Workspace):
    return APIResponse.ok(await CustomerVehicleService(svc.db, svc.customer_id).choose_default(vehicle_id))


@router.get("/vehicles/{vehicle_id}/service-history", response_model=APIResponse[dict])
async def vehicle_history(vehicle_id: UUID, svc: Workspace, page: Page = 1, page_size: Size = 20):
    return APIResponse.ok(await svc.history(vehicle_id, page, page_size))


@router.post("/attachments", response_model=APIResponse[dict], status_code=201)
async def attachment_upload(svc: Workspace, file: UploadFile = File(...),
                            purpose: Literal["PROFILE_PHOTO", "BOOKING_PHOTO", "SUPPORT_ATTACHMENT"] = Form(...)):
    return APIResponse.ok(await svc.upload(file, purpose), status_code=201)


@router.get("/attachments/{attachment_id}/download", response_class=Response,
            responses={200: {"description": "Private validated image bytes", "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "image/png", "image/webp")}}})
async def attachment_download(attachment_id: UUID, svc: Workspace):
    return await svc.download(attachment_id)


@router.delete("/attachments/{attachment_id}", response_model=APIResponse[dict])
async def attachment_delete(attachment_id: UUID, svc: Workspace):
    return APIResponse.ok(await svc.remove_attachment(attachment_id))


@router.put("/me/photo", response_model=APIResponse[dict])
async def photo_set(data: PhotoSet, svc: Workspace):
    return APIResponse.ok(await svc.set_photo(data.attachment_id))


@router.delete("/me/photo", response_model=APIResponse[dict])
async def photo_delete(svc: Workspace):
    return APIResponse.ok(await svc.remove_photo())


@router.get("/garages/{garage_id}/availability", response_model=APIResponse[dict])
async def availability(garage_id: UUID, svc: Workspace, date: date,
                       service_ids: Annotated[list[UUID], Query(min_length=1, max_length=20)]):
    return APIResponse.ok(await svc.availability(garage_id, date, service_ids))


@router.post("/bookings/quote", response_model=APIResponse[CustomerQuoteResponse])
async def quote(data: QuoteRequest, svc: Workspace):
    return APIResponse.ok(await svc.create_quote(data))


@router.post("/bookings", response_model=APIResponse[CustomerBookingResponse], status_code=201)
async def submit(data: BookingSubmit, svc: Workspace, who: Principal, key: Key):
    return APIResponse.ok(await svc.submit(data.quote_id, key, *who[:2]), status_code=201)


@router.get("/bookings", response_model=APIResponse[dict])
async def bookings(svc: Workspace, page: Page = 1, page_size: Size = 20,
                   status: BookingStatus | None = None, vehicle_id: UUID | None = None,
                   garage_id: UUID | None = None, linked_job_status: JobStatus | None = None):
    return APIResponse.ok(await svc.list_bookings(page, page_size, status, vehicle_id, garage_id, linked_job_status))


@router.get("/bookings/{booking_id}", response_model=APIResponse[CustomerBookingResponse])
async def booking_detail(booking_id: UUID, svc: Workspace):
    return APIResponse.ok(await svc.booking_row(*await svc.booking(booking_id)))


@router.get("/bookings/{booking_id}/timeline", response_model=APIResponse[dict])
async def booking_timeline(booking_id: UUID, svc: Workspace):
    return APIResponse.ok(await svc.booking_timeline(booking_id))


@router.post("/bookings/{booking_id}/cancel", response_model=APIResponse[dict])
async def booking_cancel(booking_id: UUID, data: CancelRequest, svc: Workspace):
    return APIResponse.ok(await svc.cancel(booking_id, data.reason))


@router.get("/jobs", response_model=APIResponse[dict])
async def jobs(svc: Workspace, page: Page = 1, page_size: Size = 20,
               status: JobStatus | None = None, vehicle_id: UUID | None = None):
    return APIResponse.ok(await svc.list_jobs(page, page_size, status, vehicle_id))


@router.get("/jobs/{job_id}", response_model=APIResponse[dict])
async def job_detail(job_id: UUID, svc: Workspace):
    return APIResponse.ok(await svc.job_row(await svc.job(job_id)))


@router.get("/jobs/{job_id}/timeline", response_model=APIResponse[dict])
async def job_timeline(job_id: UUID, svc: Workspace):
    return APIResponse.ok(await svc.job_timeline(job_id))


@router.get("/jobs/{job_id}/photos/{photo_index}", response_class=Response,
            responses={200: {"description": "Authorized published garage photo bytes", "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}}}}})
async def job_photo(job_id: UUID, photo_index: Annotated[int, Path(ge=0, le=4)], svc: Workspace):
    return await svc.job_photo(job_id, photo_index)


PaymentStatus = Literal["UNPAID", "PENDING", "PAID", "FAILED", "REFUNDED"]


@router.get("/invoices", response_model=APIResponse[dict])
async def invoices(svc: Workspace, page: Page = 1, page_size: Size = 20,
                   payment_status: PaymentStatus | None = None,
                   job_id: UUID | None = None, vehicle_id: UUID | None = None):
    return APIResponse.ok(await svc.list_invoices(page, page_size, payment_status, job_id, vehicle_id))


@router.get("/invoices/{invoice_id}", response_model=APIResponse[dict])
async def invoice_detail(invoice_id: UUID, svc: Workspace):
    return APIResponse.ok(await svc.invoice_row(await svc.invoice(invoice_id)))


PDF_RESPONSE = {200: {"description": "Authenticated PDF download", "content": {
    "application/pdf": {"schema": {"type": "string", "format": "binary"}}}}}


@router.get("/invoices/{invoice_id}/pdf", response_class=Response, responses=PDF_RESPONSE)
async def invoice_pdf(invoice_id: UUID, svc: Workspace):
    return await svc.invoice_pdf(invoice_id)


class PaymentRequest(StrictInput):
    return_path: Literal["/payments/result"] | None = None


@router.post("/invoices/{invoice_id}/payment-attempts", response_model=APIResponse[dict],
             description="Razorpay pending by customer choice. Always returns 503 after invoice ownership validation; no checkout/order is created.")
async def payment_create(invoice_id: UUID, data: PaymentRequest, key: Key, svc: Workspace):
    await svc.invoice(invoice_id)
    fail("PAYMENT_PROVIDER_NOT_CONFIGURED", 503)


@router.get("/payments/{payment_id}", response_model=APIResponse[dict])
async def payment_detail(payment_id: UUID, svc: Workspace):
    return APIResponse.ok(await svc.payment_row(await svc.source(payment_id, "PAYMENT")))


@router.get("/invoices/{invoice_id}/payment-attempts", response_model=APIResponse[dict])
async def payment_attempts(invoice_id: UUID, svc: Workspace, page: Page = 1, page_size: Size = 20):
    return APIResponse.ok(await svc.attempts(invoice_id, page, page_size))


@router.get("/payments/{payment_id}/receipt", response_class=Response, responses=PDF_RESPONSE)
async def payment_receipt(payment_id: UUID, svc: Workspace):
    return await svc.receipt(payment_id)


@router.put("/devices/{installation_id}", response_model=APIResponse[dict])
async def device(installation_id: Installation, data: DeviceRequest, svc: Workspace, who: Principal):
    return APIResponse.ok(await svc.register_device(installation_id, data, who[2].id))


@router.delete("/devices/{installation_id}", response_model=APIResponse[dict])
async def device_delete(installation_id: Installation, svc: Workspace):
    return APIResponse.ok(await svc.detach_device(installation_id))


@router.get("/notifications", response_model=APIResponse[dict])
async def notifications(svc: Workspace, page: Page = 1, page_size: Size = 20, category: Category | None = None):
    return APIResponse.ok(await svc.notifications(category, page, page_size))


@router.patch("/notifications/{notification_id}", response_model=APIResponse[dict])
async def notification_read(notification_id: UUID, data: NotificationRead, svc: Workspace):
    row = await svc.resource(notification_id, "NOTIFICATION")
    row.payload = {**row.payload, "is_read": True}
    return APIResponse.ok(svc.row(row))


@router.post("/notifications/read-all", response_model=APIResponse[dict])
async def notifications_read_all(data: ReadAll, svc: Workspace):
    return APIResponse.ok(await svc.mark_all(data.category))


@router.post("/conversations", response_model=APIResponse[dict], status_code=201)
async def conversation_create(data: ConversationStart, svc: Workspace, response: Response):
    result, created = await svc.start_conversation(data)
    response.status_code = 201 if created else 200
    return APIResponse.ok(result, status_code=response.status_code)


@router.get("/conversations", response_model=APIResponse[dict])
async def conversations(svc: Workspace, page: Page = 1, page_size: Size = 20):
    return APIResponse.ok(await svc.page(svc.query("CONVERSATION").order_by(
        CustomerResource.created_at.desc(), CustomerResource.id), page, page_size))


@router.get("/conversations/{conversation_id}/messages", response_model=APIResponse[dict])
async def conversation_messages(conversation_id: UUID, svc: Workspace,
                                cursor: UUID | None = None, limit: Limit = 50):
    row = await svc.resource(conversation_id, "CONVERSATION")
    return APIResponse.ok(await svc.cursor_messages(row, "MESSAGE", cursor, limit))


@router.post("/conversations/{conversation_id}/messages", response_model=APIResponse[dict], status_code=201)
async def message_send(conversation_id: UUID, data: MessageSend, svc: Workspace, response: Response):
    result, created = await svc.conversation_send(conversation_id, data)
    response.status_code = 201 if created else 200
    return APIResponse.ok(result, status_code=response.status_code)


@router.post("/conversations/{conversation_id}/read", response_model=APIResponse[dict])
async def conversation_read(conversation_id: UUID, data: ReadMarker, svc: Workspace):
    return APIResponse.ok(await svc.mark_conversation(conversation_id, data.last_read_message_id))


@router.post("/jobs/{job_id}/review", response_model=APIResponse[dict], status_code=201)
async def review_create(job_id: UUID, data: ReviewCreate, svc: Workspace):
    return APIResponse.ok(await svc.create_review(job_id, data), status_code=201)


@router.get("/me/reviews", response_model=APIResponse[dict])
async def reviews(svc: Workspace, page: Page = 1, page_size: Size = 20):
    return APIResponse.ok(await svc.page(svc.query("REVIEW").order_by(
        CustomerResource.created_at.desc(), CustomerResource.id), page, page_size))


@router.patch("/reviews/{review_id}", response_model=APIResponse[dict])
async def review_edit(review_id: UUID, data: ReviewPatch, svc: Workspace):
    return APIResponse.ok(await svc.edit_review(review_id, data))


@router.post("/support/tickets", response_model=APIResponse[dict], status_code=201)
async def ticket_create(data: TicketCreate, svc: Workspace):
    return APIResponse.ok(await svc.create_ticket(data), status_code=201)


@router.get("/support/tickets", response_model=APIResponse[dict])
async def tickets(svc: Workspace, page: Page = 1, page_size: Size = 20,
                  status: Literal["OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "RESOLVED", "CLOSED"] | None = None):
    query = svc.query("TICKET")
    if status:
        query = query.where(CustomerResource.status == status)
    return APIResponse.ok(await svc.page(query.order_by(CustomerResource.created_at.desc(), CustomerResource.id),
                                        page, page_size))


@router.get("/support/tickets/{ticket_id}", response_model=APIResponse[dict])
async def ticket_detail(ticket_id: UUID, svc: Workspace):
    return APIResponse.ok(svc.row(await svc.resource(ticket_id, "TICKET")))


@router.get("/support/tickets/{ticket_id}/messages", response_model=APIResponse[dict])
async def ticket_messages(ticket_id: UUID, svc: Workspace, cursor: UUID | None = None, limit: Limit = 50):
    row = await svc.resource(ticket_id, "TICKET")
    return APIResponse.ok(await svc.cursor_messages(row, "TICKET_MESSAGE", cursor, limit))


@router.post("/support/tickets/{ticket_id}/messages", response_model=APIResponse[dict], status_code=201)
async def ticket_reply(ticket_id: UUID, data: TicketReply, svc: Workspace, response: Response):
    result, created = await svc.ticket_send(ticket_id, data)
    response.status_code = 201 if created else 200
    return APIResponse.ok(result, status_code=response.status_code)
