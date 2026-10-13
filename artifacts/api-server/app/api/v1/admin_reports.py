import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from app.api.v1.admin import DBSession
from app.api.v1.admin_operations import Key
from app.core.admin_privacy import AdminPrivacyRoute
from app.core.admin_read_filters import reject_unknown_admin_query
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.schemas.admin_operations import ExportRequest
from app.schemas.response import APIResponse
from app.services.admin_export_service import AdminExportService, export_row, render_report

router = APIRouter(route_class=AdminPrivacyRoute, dependencies=[
    Depends(get_current_admin), Depends(reject_unknown_admin_query)])


@router.post("/reports/exports", response_model=APIResponse, status_code=202)
async def request_export(data: ExportRequest, admin: CurrentAdmin, session: DBSession, idempotency_key: Key):
    result = await AdminExportService(session).request_export(data, idempotency_key)
    return APIResponse.ok(data=result, status_code=202)


@router.get("/reports/exports/{export_id}", response_model=APIResponse)
async def report_status(export_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminExportService(session)
    result = export_row(await service.get_export(export_id))
    await service.audit("report.status", export_id)
    return APIResponse.ok(data=result)


@router.get("/reports/exports/{export_id}/download")
async def download_report(export_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminExportService(session)
    resource = await service.get_export(export_id)
    if resource.status != "READY":
        raise HTTPException(409, "EXPORT_NOT_READY")
    body, mime = render_report(resource.payload, resource.payload["format"])
    await service.audit("report.download", export_id, {"row_count": resource.payload["row_count"]})
    return Response(content=body, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{resource.payload["report_type"].lower()}.{resource.payload["format"].lower()}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })
