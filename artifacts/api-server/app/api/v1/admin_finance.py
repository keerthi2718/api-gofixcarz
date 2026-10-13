import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Query
from app.api.v1.admin import DBSession, Page, PageSize
from app.api.v1.admin_monitoring import Filters
from app.core.admin_privacy import AdminPrivacyRoute
from app.core.admin_read_filters import reject_unknown_admin_query
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.schemas.response import APIResponse
from app.services.admin_metrics_service import AdminMetricsService
from app.services.admin_operations_service import AdminOperationsService, record_row
from app.models.admin_operations import SourceRecord

router = APIRouter(route_class=AdminPrivacyRoute, dependencies=[
    Depends(get_current_admin), Depends(reject_unknown_admin_query)])


@router.get("/finance/summary", response_model=APIResponse)
async def finance_summary(admin: CurrentAdmin, session: DBSession, filters: Filters, snapshot_id: uuid.UUID | None = None):
    service = AdminMetricsService(session)
    snapshot = await service.dataset(filters, snapshot_id)
    result = {**service.metadata(snapshot), **service.finance(snapshot, filters)}
    await service.audit("finance.summary")
    return APIResponse.ok(data=result)


@router.get("/finance/trends", response_model=APIResponse)
async def finance_trends(admin: CurrentAdmin, session: DBSession, filters: Filters, snapshot_id: uuid.UUID | None = None,
                         period: Literal["daily", "weekly", "monthly"] = "daily"):
    service = AdminMetricsService(session)
    snapshot = await service.dataset(filters, snapshot_id)
    await service.audit("finance.trends")
    return APIResponse.ok(data={**service.metadata(snapshot), "period": period,
                               "series": service.trends(snapshot, filters, period, finance=True)})


async def collection(session, kind, filters, status, customer_id, page, page_size, parent_id=None):
    service = AdminOperationsService(session)
    result = await service.paged(service.records_query(kind, filters, status, customer_id, parent_id), page, page_size)
    result.update(filters=filters.metadata(), money_unit="paise", currency="INR", source_status="RECORDED_EVENTS" if result["total"] else "NO_RECORDS")
    await service.audit(kind.lower()+".list")
    return APIResponse.ok(data=result)


@router.get("/invoices", response_model=APIResponse)
async def invoices(admin: CurrentAdmin, session: DBSession, filters: Filters,
                   status: Literal["DRAFT", "ISSUED", "PAID", "VOID"] | None = None, customer_id: uuid.UUID | None = None,
                   page: Page = 1, page_size: PageSize = 20):
    return await collection(session, "INVOICE", filters, status, customer_id, page, page_size)


@router.get("/payments", response_model=APIResponse)
async def payments(admin: CurrentAdmin, session: DBSession, filters: Filters,
                   status: Literal["CREATED", "PENDING", "CAPTURED", "FAILED"] | None = None, customer_id: uuid.UUID | None = None,
                   invoice_id: uuid.UUID | None = None, page: Page = 1, page_size: PageSize = 20):
    return await collection(session, "PAYMENT", filters, status, customer_id, page, page_size, invoice_id)


@router.get("/refunds", response_model=APIResponse)
async def refunds(admin: CurrentAdmin, session: DBSession, filters: Filters,
                  status: Literal["PENDING", "SETTLED", "FAILED"] | None = None,
                  customer_id: uuid.UUID | None = None, payment_id: uuid.UUID | None = None,
                  page: Page = 1, page_size: PageSize = 20):
    return await collection(session, "REFUND", filters, status, customer_id, page, page_size, payment_id)


@router.get("/disputes", response_model=APIResponse)
async def disputes(admin: CurrentAdmin, session: DBSession, filters: Filters,
                   status: Literal["OPEN", "UNDER_REVIEW", "WON", "LOST", "CLOSED"] | None = None,
                   customer_id: uuid.UUID | None = None, page: Page = 1, page_size: PageSize = 20):
    return await collection(session, "DISPUTE", filters, status, customer_id, page, page_size)


async def detail(session, resource_id, kind):
    service = AdminOperationsService(session)
    record = await service.record(resource_id, kind)
    result = record_row(record)
    if kind in ("INVOICE", "PAYMENT"):
        result["linked_records"] = (await service.paged(service.records_query(
            "PAYMENT" if kind == "INVOICE" else "REFUND", parent_id=resource_id)))["items"]
        result["preview_limit"] = 20
    await service.audit(kind.lower()+".read", resource_id)
    return APIResponse.ok(data=result)


@router.get("/invoices/{invoice_id}", response_model=APIResponse)
async def invoice_detail(invoice_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    return await detail(session, invoice_id, "INVOICE")


@router.get("/payments/{payment_id}", response_model=APIResponse)
async def payment_detail(payment_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    return await detail(session, payment_id, "PAYMENT")


@router.get("/disputes/{dispute_id}", response_model=APIResponse)
async def dispute_detail(dispute_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    return await detail(session, dispute_id, "DISPUTE")


@router.get("/invoices/{invoice_id}/payment-attempts", response_model=APIResponse)
async def payment_attempts(invoice_id: uuid.UUID, admin: CurrentAdmin, session: DBSession,
                           page: Page = 1, page_size: PageSize = 20):
    service = AdminOperationsService(session)
    await service.record(invoice_id, "INVOICE")
    result = await service.paged(service.records_query("PAYMENT", parent_id=invoice_id), page, page_size)
    await service.audit("invoice.payment_attempts", invoice_id)
    return APIResponse.ok(data=result)
