"""Published customer projections and financial-source reads (no inferred captures)."""
import io
from html import escape
from uuid import UUID
from sqlalchemy import case, func, select
from fastapi.responses import Response
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from app.models.job import Job
from app.models.job_timeline import JobTimeline
from app.models.booking import Booking
from app.models.customer_workspace import CustomerBookingLink, CustomerResource
from app.models.admin_operations import SourceRecord
from app.models.garage import Garage
from app.services.customer_booking_service import CustomerBookingService
from app.services.customer_otp_service import fail


def pdf_document(title, lines, filename):
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 16)]
    for line in lines:
        story.extend([Paragraph(escape(str(line)), styles["BodyText"]), Spacer(1, 8)])
    SimpleDocTemplate(output).build(story)
    return Response(output.getvalue(), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


class CustomerTrackingService(CustomerBookingService):
    async def booking_timeline(self, identifier):
        booking, link = await self.booking(identifier)
        events = (await self.db.execute(select(SourceRecord).where(
            SourceRecord.kind == "BOOKING_EVENT", SourceRecord.booking_id == identifier
        ).order_by(SourceRecord.occurred_at, SourceRecord.id))).scalars().all()
        items = [{"event": "PENDING", "occurred_at": booking.created_at}]
        items.extend({"event": row.status, "occurred_at": row.occurred_at,
                      "reason": row.payload.get("reason")} for row in events)
        jobs = (await self.db.execute(select(Job).where(Job.booking_id == identifier,
                                                       Job.deleted_at.is_(None)))).scalars().all()
        items.extend({"event": "JOB_CREATED", "job_id": row.id, "occurred_at": row.created_at} for row in jobs)
        items.sort(key=lambda item: item["occurred_at"])
        return {"items": items}

    async def job_row(self, job):
        link = await self.db.get(CustomerBookingLink, job.booking_id)
        garage = await self.db.get(Garage, job.garage_id)
        published = (await self.db.execute(self.query("JOB_PUBLICATION").where(
            CustomerResource.dedupe_key == str(job.id)))).scalar_one_or_none()
        projection = dict(published.payload) if published else {
            "findings": [], "notes": None, "services": [], "parts": [], "labour": []}
        keys = projection.pop("photo_keys", [])
        projection["photos"] = [{"download_path": f"/api/v1/customer-app/jobs/{job.id}/photos/{index}"}
                                for index, key in enumerate(keys)]
        return {"id": job.id, "job_number": job.job_number, "booking_id": job.booking_id,
                "vehicle_id": link.vehicle_id, "garage": {"id": garage.id, "name": garage.name},
                "status": job.status.value, "created_at": job.created_at, "completed_at": job.completed_at,
                "published": published is not None,
                **projection}

    async def job_photo(self, identifier, index):
        job = await self.job(identifier)
        publication = (await self.db.execute(self.query("JOB_PUBLICATION").where(
            CustomerResource.dedupe_key == str(job.id)))).scalar_one_or_none()
        keys = publication.payload.get("photo_keys", []) if publication else []
        if index >= len(keys) or keys[index] not in (job.photos or []):
            fail("RESOURCE_NOT_FOUND", 404)
        from app.utils.s3 import _client, is_garage_object_key
        from app.core.config import settings
        from app.services.customer_attachment_service import sanitize_image, MAX_SIZE
        from starlette.concurrency import run_in_threadpool
        from botocore.exceptions import BotoCoreError, ClientError
        if not is_garage_object_key(keys[index], job.garage_id):
            fail("RESOURCE_NOT_FOUND", 404)
        def read():
            result = _client().get_object(Bucket=settings.S3_BUCKET_NAME, Key=keys[index])
            with result["Body"] as stream:
                return stream.read(MAX_SIZE + 1), result["ContentType"]
        try:
            contents, content_type = await run_in_threadpool(read)
        except (BotoCoreError, ClientError):
            fail("ATTACHMENT_STORAGE_UNAVAILABLE", 503)
        if len(contents) > MAX_SIZE:
            fail("ATTACHMENT_TOO_LARGE", 413)
        clean, (mime, extension) = await run_in_threadpool(sanitize_image, contents, content_type)
        return Response(clean, media_type=mime, headers={
            "Content-Disposition": f'inline; filename="job-photo-{index}.{extension}"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    async def list_jobs(self, page, size, status=None, vehicle_id=None):
        query = select(Job).join(CustomerBookingLink, CustomerBookingLink.booking_id == Job.booking_id).where(
            CustomerBookingLink.customer_id == self.customer_id, Job.deleted_at.is_(None))
        if status:
            query = query.where(Job.status == status)
        if vehicle_id:
            query = query.where(CustomerBookingLink.vehicle_id == vehicle_id)
        return await self.page(query.order_by(Job.created_at.desc(), Job.id), page, size, self.job_row)

    async def job_timeline(self, identifier):
        await self.job(identifier)
        rows = (await self.db.execute(select(JobTimeline).where(
            JobTimeline.job_id == identifier).order_by(JobTimeline.created_at, JobTimeline.id))).scalars().all()
        # Legacy notes have no publication flag: never expose them.
        return {"items": [{"id": row.id, "status": row.status, "occurred_at": row.created_at} for row in rows]}

    async def history(self, identifier, page, size):
        await self.vehicle(identifier, archived=True)
        query = select(Job).join(CustomerBookingLink, CustomerBookingLink.booking_id == Job.booking_id).where(
            CustomerBookingLink.customer_id == self.customer_id, CustomerBookingLink.vehicle_id == identifier,
            Job.status == "COMPLETED", Job.deleted_at.is_(None))
        async def render(job):
            result = await self.job_row(job)
            invoice = (await self.db.execute(select(SourceRecord.id).where(
                SourceRecord.kind == "INVOICE", SourceRecord.job_id == job.id,
                SourceRecord.customer_id == self.customer_id,
                SourceRecord.status.in_(["ISSUED", "PAID"])).limit(1))).scalar_one_or_none()
            return {"booking_id": job.booking_id, "job_id": job.id, "job_status": "COMPLETED",
                    "completed_at": job.completed_at, "garage": result["garage"], "invoice_id": invoice}
        return await self.page(query.order_by(Job.completed_at.desc(), Job.id), page, size, render)

    def invoice_query(self):
        # Trusted financial sources, customer identity and completed job required.
        return select(SourceRecord).join(Job, Job.id == SourceRecord.job_id).where(
            SourceRecord.kind == "INVOICE", SourceRecord.customer_id == self.customer_id,
            SourceRecord.status.in_(["ISSUED", "PAID"]), Job.status == "COMPLETED",
            Job.deleted_at.is_(None))

    async def invoice(self, identifier):
        row = (await self.db.execute(self.invoice_query().where(SourceRecord.id == identifier))).scalar_one_or_none()
        if not row:
            fail("RESOURCE_NOT_FOUND", 404)
        return row

    async def invoice_row(self, row):
        payments = (await self.db.execute(select(SourceRecord).where(
            SourceRecord.kind == "PAYMENT", SourceRecord.parent_id == row.id,
            SourceRecord.customer_id == self.customer_id))).scalars().all()
        captured = sum(p.amount or 0 for p in payments if p.status == "CAPTURED")
        refunds = (await self.db.execute(select(SourceRecord.amount).where(
            SourceRecord.kind == "REFUND", SourceRecord.parent_id.in_([p.id for p in payments]),
            SourceRecord.customer_id == self.customer_id, SourceRecord.status == "SETTLED"))).scalars().all()
        refunded = sum(refunds)
        status = "PAID" if captured >= row.amount else "UNPAID"
        if captured and refunded >= captured:
            status = "REFUNDED"
        elif captured < row.amount and any(p.status in {"CREATED", "PENDING"} for p in payments):
            status = "PENDING"
        elif not captured and payments and all(p.status == "FAILED" for p in payments):
            status = "FAILED"
        result = {"id": row.id, "job_id": row.job_id, "booking_id": row.booking_id,
                  "garage_id": row.garage_id, "issued_at": row.occurred_at,
                  "currency": row.currency, "total": row.amount, "payment_status": status,
                  "paid_amount": captured, "refunded_amount": refunded,
                  "balance_due": max(0, row.amount - captured)}
        for name in ("invoice_number", "subtotal", "tax_amount", "discount_amount"):
            result[name] = row.payload.get(name)
        if row.booking_id:
            link = await self.db.get(CustomerBookingLink, row.booking_id)
            result["vehicle_id"] = link.vehicle_id if link and link.customer_id == self.customer_id else None
        return result

    async def list_invoices(self, page, size, payment_status=None, job_id=None, vehicle_id=None):
        query = self.invoice_query().order_by(SourceRecord.occurred_at.desc(), SourceRecord.id)
        if job_id:
            query = query.where(SourceRecord.job_id == job_id)
        if vehicle_id:
            query = query.join(CustomerBookingLink, CustomerBookingLink.booking_id == SourceRecord.booking_id).where(
                CustomerBookingLink.customer_id == self.customer_id, CustomerBookingLink.vehicle_id == vehicle_id)
        if payment_status:
            from sqlalchemy.orm import aliased
            payment, refund = aliased(SourceRecord), aliased(SourceRecord)
            owned = (payment.kind == "PAYMENT", payment.parent_id == SourceRecord.id,
                     payment.customer_id == self.customer_id)
            captured = select(func.coalesce(func.sum(payment.amount), 0)).where(
                *owned, payment.status == "CAPTURED").correlate(SourceRecord).scalar_subquery()
            refunded = select(func.coalesce(func.sum(refund.amount), 0)).join(
                payment, refund.parent_id == payment.id).where(
                    *owned, refund.kind == "REFUND", refund.status == "SETTLED",
                    refund.customer_id == self.customer_id).correlate(SourceRecord).scalar_subquery()
            pending = select(payment.id).where(*owned, payment.status.in_(["CREATED", "PENDING"])).correlate(SourceRecord).exists()
            failed = select(payment.id).where(*owned, payment.status == "FAILED").correlate(SourceRecord).exists()
            nonfailed = select(payment.id).where(*owned, payment.status != "FAILED").correlate(SourceRecord).exists()
            state = case(
                ((captured > 0) & (refunded >= captured), "REFUNDED"),
                (captured >= SourceRecord.amount, "PAID"), (pending, "PENDING"),
                ((captured == 0) & failed & ~nonfailed, "FAILED"), else_="UNPAID")
            query = query.where(state == payment_status)
        return await self.page(query, page, size, self.invoice_row)

    async def invoice_pdf(self, identifier):
        row = await self.invoice(identifier)
        data = await self.invoice_row(row)
        garage = await self.db.get(Garage, row.garage_id)
        lines = [f"Garage: {garage.name}", f"Address: {garage.address or 'Not supplied'}",
                 f"Invoice number: {data['invoice_number'] or row.external_id}",
                 f"Issued: {row.occurred_at.isoformat()}", f"Job: {row.job_id}"]
        lines += [f"{name}: {data[name]} paise" for name in (
            "subtotal", "tax_amount", "discount_amount", "total", "paid_amount", "balance_due")]
        lines += [f"Currency: {data['currency']}", f"Payment status: {data['payment_status']}",
                  "Development invoice representation. Legal tax-invoice fields require production billing review."]
        return pdf_document("GoFixCarz Invoice", lines, f"invoice-{row.id}.pdf")

    async def payment_row(self, row):
        await self.invoice(row.parent_id)
        return {"id": row.id, "invoice_id": row.parent_id, "amount": row.amount,
                "currency": row.currency, "status": {
                    "CAPTURED": "PAID", "CREATED": "PENDING"}.get(row.status, row.status),
                "occurred_at": row.occurred_at, "failure_code": row.payload.get("failure_code"),
                "gateway_reference": row.payload.get("gateway_reference")}

    async def attempts(self, identifier, page, size):
        await self.invoice(identifier)
        return await self.page(select(SourceRecord).where(
            SourceRecord.kind == "PAYMENT", SourceRecord.parent_id == identifier,
            SourceRecord.customer_id == self.customer_id).order_by(
                SourceRecord.occurred_at.desc(), SourceRecord.id), page, size, self.payment_row)

    async def receipt(self, identifier):
        row = await self.source(identifier, "PAYMENT")
        data = await self.payment_row(row)
        if row.status != "CAPTURED":
            fail("RECEIPT_UNAVAILABLE", 409)
        return pdf_document("GoFixCarz Payment Receipt", [
            f"Payment ID: {row.id}", f"Invoice: {row.parent_id}", f"Amount: {row.amount} paise",
            f"Currency: {row.currency}", f"Confirmed: {row.occurred_at.isoformat()}",
            f"Gateway reference: {data['gateway_reference'] or 'Not supplied'}",
        ], f"receipt-{row.id}.pdf")
