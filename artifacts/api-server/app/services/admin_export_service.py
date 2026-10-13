"""Bounded, private exports. File bytes are generated on download, never stored in SQL."""
import csv
import io
import json
import uuid
import zipfile
from datetime import timedelta
from xml.sax.saxutils import escape
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.core.admin_policy import require_permission
from app.core.admin_read_filters import AdminReadFilters
from app.core.config import settings
from app.models.admin_operations import AdminResource
from app.services.admin_metrics_service import AdminMetricsService
from app.services.admin_operations_service import fingerprint, now

REPORT_PERMISSIONS = {
    "OPERATIONS": ["garages.read", "jobs.read", "bookings.read"],
    "FINANCE": ["finance.read"],
    "GARAGE_OWNER_PERFORMANCE": ["owner_statistics.read"],
}


def enforce_report(session, report_type):
    require_permission(session, "reports.export")
    for permission in REPORT_PERMISSIONS[report_type]:
        require_permission(session, permission)


def scalar(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if value is None:
        return ""
    if isinstance(value, str):
        value = "".join(character for character in value if ord(character) >= 32 or character in "\t\n\r")
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


def render_report(payload, format):
    rows = payload["rows"]
    columns = sorted({key for row in rows for key in row})
    metadata = {key: payload[key] for key in ("filters", "generated_at", "snapshot_id", "row_count", "source_totals", "metric_definitions")}
    matrix = [["metadata", json.dumps(metadata, sort_keys=True)], columns]
    matrix += [[scalar(row.get(column)) for column in columns] for row in rows]
    if format == "CSV":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerows(matrix)
        return output.getvalue().encode("utf-8-sig"), "text/csv"
    sheet = []
    for number, row in enumerate(matrix, 1):
        if any(len(str(cell)) > 32767 for cell in row):
            raise ValueError("XLSX cell size limit")
        cells = "".join(f'<c t="inlineStr"><is><t xml:space="preserve">{escape(str(cell))}</t></is></c>' for cell in row)
        sheet.append(f'<row r="{number}">{cells}</row>')
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>''')
        archive.writestr("_rels/.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        archive.writestr("xl/workbook.xml", '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        archive.writestr("xl/_rels/workbook.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+"".join(sheet)+"</sheetData></worksheet>")
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class AdminExportService(AdminMetricsService):
    async def request_export(self, data, key):
        enforce_report(self.session, data.report_type)
        if data.exclude_inactive and data.report_type != "GARAGE_OWNER_PERFORMANCE":
            raise HTTPException(422, "exclude_inactive applies only to owner performance")
        if data.filters.service_id:
            raise HTTPException(422, "SERVICE_FILTER_UNAVAILABLE: jobs do not persist canonical service IDs")
        existing = await self.idempotent("EXPORT", key, data.model_dump(mode="json"))
        if existing:
            return export_row(existing)
        filters = AdminReadFilters(**data.filters.model_dump(exclude={"service_id"}))
        snapshot = await self.dataset(filters, data.snapshot_id, data.exclude_inactive)
        if data.report_type == "GARAGE_OWNER_PERFORMANCE":
            rows = self.owner_rows(snapshot, filters)
            totals = self.totals(rows)
            if "finance.read" not in self.session.info["admin_access"]["permissions"]:
                from app.core.admin_privacy import FINANCE_KEYS
                rows = [{k: v for k, v in row.items() if k not in FINANCE_KEYS} for row in rows]
                totals = {k: v for k, v in totals.items() if k not in FINANCE_KEYS}
        elif data.report_type == "FINANCE":
            rows = [r for r in snapshot.payload["records"] if r["kind"] in ("INVOICE", "PAYMENT", "REFUND", "DISPUTE")
                    and self.in_window(r["occurred_at"], filters)]
            totals = self.finance(snapshot, filters)
        else:
            window = self.normalized(filters)
            jobs = [j for j in snapshot.payload["jobs"] if self.in_window(j["created_at"], window)]
            bookings = snapshot.payload["bookings"]
            rows = [{"record_type": "JOB", **j} for j in jobs] + [{"record_type": "BOOKING", **b} for b in bookings]
            totals = {"jobs_created": len(jobs), "bookings_created": len(bookings)}
        if len(rows) > settings.ADMIN_MAX_REPORT_ROWS:
            raise HTTPException(413, "EXPORT_TOO_LARGE")
        resource = AdminResource(
            id=uuid.uuid4(), kind="EXPORT", status="QUEUED", actor_id=snapshot.actor_id,
            idempotency_key=key, fingerprint=fingerprint(data.model_dump(mode="json")),
            expires_at=now()+timedelta(hours=24),
            payload=jsonable_encoder({
                "scope_signature": self.scope_signature(), "report_type": data.report_type, "format": data.format,
                **self.metadata(snapshot), "row_count": len(rows), "rows": rows, "source_totals": totals,
            }),
        )
        self.session.add(resource)
        await self.audit("report.request", resource.id, {"report_type": data.report_type, "format": data.format, "rows": len(rows)})
        return export_row(resource)

    async def get_export(self, export_id):
        resource = await self.resource(export_id, "EXPORT")
        enforce_report(self.session, resource.payload["report_type"])
        return resource

    @staticmethod
    async def process_queue(session):
        jobs = (await session.execute(select(AdminResource).where(
            AdminResource.kind == "EXPORT", AdminResource.status == "QUEUED",
        ).order_by(AdminResource.created_at).limit(5).with_for_update(skip_locked=True))).scalars().all()
        for resource in jobs:
            if resource.expires_at <= now():
                resource.status = "EXPIRED"
                continue
            resource.status = "PROCESSING"
            try:
                data, _ = render_report(resource.payload, resource.payload["format"])
                if len(data) > 10*1024*1024:
                    raise ValueError("size")
                resource.status = "READY"
            except Exception:
                resource.status = "FAILED"
                resource.payload = {**resource.payload, "error": "Report generation failed or exceeded the development size limit"}


def export_row(resource):
    payload = resource.payload
    return {key: payload[key] for key in (
        "report_type", "format", "filters", "snapshot_id", "generated_at", "row_count", "source_totals", "metric_definitions",
    )} | {
        "id": resource.id, "status": resource.status, "expires_at": resource.expires_at,
        "error": payload.get("error"), "download_path": f"/api/v1/admin/reports/exports/{resource.id}/download" if resource.status == "READY" else None,
    }
