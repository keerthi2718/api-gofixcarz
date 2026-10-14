"""Customer activity, conversations, moderated reviews and support."""
import hashlib
from datetime import timedelta
from uuid import UUID
from sqlalchemy import func, select, update
from app.core.customer_security import now
from app.models.customer_workspace import CustomerResource
from app.services.customer_tracking_service import CustomerTrackingService
from app.services.customer_otp_service import fail


class CustomerActivityService(CustomerTrackingService):
    async def register_device(self, installation_id, data, session_id):
        await self.lock("installation", installation_id)
        await self.lock("push-token", hashlib.sha256(data.push_token.encode()).hexdigest())
        # A shared app installation must stop receiving the previous account's events.
        await self.db.execute(update(CustomerResource).where(
            CustomerResource.kind == "DEVICE",
            (CustomerResource.dedupe_key == installation_id) |
            (CustomerResource.payload["push_token"].astext == data.push_token)
        ).values(status="DETACHED", payload={}))
        existing = (await self.db.execute(self.query("DEVICE").where(
            CustomerResource.dedupe_key == installation_id))).scalar_one_or_none()
        payload = {**data.model_dump(), "session_id": str(session_id)}
        if existing:
            existing.status, existing.payload = "ACTIVE", payload
        else:
            await self.add("DEVICE", payload, key=installation_id)
        return {"installation_id": installation_id, "registered": True, "push_delivery_configured": False}

    async def detach_device(self, installation_id):
        row = (await self.db.execute(self.query("DEVICE").where(
            CustomerResource.dedupe_key == installation_id))).scalar_one_or_none()
        if row:
            row.status, row.payload = "DETACHED", {}
        return {"installation_id": installation_id, "removed": True}

    async def notifications(self, category, page, size):
        query = self.query("NOTIFICATION")
        if category:
            query = query.where(CustomerResource.payload["category"].astext == category)
        unread = (await self.db.execute(select(func.count()).select_from(
            query.where(CustomerResource.payload["is_read"].as_boolean().is_(False)).subquery()
        ))).scalar_one()
        result = await self.page(query.order_by(CustomerResource.created_at.desc(), CustomerResource.id), page, size)
        result["unread_count"] = unread
        return result

    async def mark_all(self, category):
        query = self.query("NOTIFICATION")
        if category:
            query = query.where(CustomerResource.payload["category"].astext == category)
        count = 0
        for row in (await self.db.execute(query)).scalars().all():
            if not row.payload["is_read"]:
                row.payload = {**row.payload, "is_read": True}
                count += 1
        return {"marked_read": count}

    async def start_conversation(self, data):
        if data.job_id:
            job = await self.job(data.job_id)
            booking_id = job.booking_id
        else:
            booking_id = data.booking_id
        booking, link = await self.booking(booking_id)
        key = str(booking_id)  # Same conversation before and after conversion.
        row = (await self.db.execute(self.query("CONVERSATION").where(
            CustomerResource.dedupe_key == key))).scalar_one_or_none()
        if row:
            return self.row(row), False
        row = await self.add("CONVERSATION", {"booking_id": booking_id, "last_read_message_id": None},
                             garage_id=booking.garage_id, key=key)
        return self.row(row), True

    async def conversation_send(self, identifier, data, *, sender_role="CUSTOMER", sender_id=None):
        conversation = await self.resource(identifier, "CONVERSATION")
        key = hashlib.sha256(f"{identifier}:{sender_role}:{sender_id or self.customer_id}:{data.client_message_id}".encode()).hexdigest()
        previous = (await self.db.execute(self.query("MESSAGE").where(
            CustomerResource.dedupe_key == key))).scalar_one_or_none()
        if previous:
            if previous.payload["text"] != data.text:
                fail("IDEMPOTENCY_CONFLICT", 409)
            return self.row(previous), False
        booking, link = await self.booking(UUID(conversation.payload["booking_id"]))
        detail = await self.booking_row(booking, link)
        if booking.status.value in {"CANCELLED", "REJECTED", "EXPIRED"} or detail["linked_job_status"] in {"COMPLETED", "CANCELLED"}:
            fail("CONVERSATION_READ_ONLY", 409)
        row = await self.add("MESSAGE", {
            "client_message_id": data.client_message_id, "text": data.text,
            "sender_role": sender_role, "sent_at": now(),
        }, parent_id=identifier, garage_id=conversation.garage_id, key=key)
        if sender_role != "CUSTOMER":
            await self.notify("MESSAGES", "New garage message", identifier, f"message:{row.id}")
        return self.row(row), True

    async def mark_conversation(self, identifier, marker_id):
        conversation = await self.resource(identifier, "CONVERSATION")
        marker = await self.resource(marker_id, "MESSAGE")
        if marker.parent_id != conversation.id:
            fail("READ_MARKER_INVALID", 422)
        old_id = conversation.payload.get("last_read_message_id")
        if old_id:
            old = await self.resource(UUID(old_id), "MESSAGE")
            if (marker.created_at, marker.id) < (old.created_at, old.id):
                fail("READ_MARKER_BACKWARDS", 409)
        conversation.payload = {**conversation.payload, "last_read_message_id": str(marker_id)}
        return {"last_read_message_id": marker_id}

    async def create_review(self, identifier, data):
        job = await self.job(identifier)
        if job.status.value != "COMPLETED":
            fail("JOB_NOT_COMPLETED", 409)
        if (await self.db.execute(self.query("REVIEW").where(
            CustomerResource.dedupe_key == str(identifier)))).scalar_one_or_none():
            fail("REVIEW_ALREADY_EXISTS", 409)
        row = await self.add("REVIEW", {"job_id": identifier, "garage_id": job.garage_id,
                                       **data.model_dump()}, status="PENDING",
                             garage_id=job.garage_id, key=str(identifier))
        await self.notify("REVIEWS", "Review submitted for moderation", row.id, f"review:{row.id}")
        return self.row(row)

    async def edit_review(self, identifier, data):
        row = await self.resource(identifier, "REVIEW")
        if now() > row.created_at + timedelta(days=7):
            fail("REVIEW_EDIT_WINDOW_EXPIRED", 409)
        row.payload = {**row.payload, **data.model_dump(exclude_unset=True)}
        row.status = "PENDING"
        return self.row(row)

    async def validate_ticket_context(self, data):
        booking_id, job_id, garage_id = data.booking_id, data.job_id, None
        if data.payment_id:
            payment = await self.source(data.payment_id, "PAYMENT")
            if data.invoice_id and data.invoice_id != payment.parent_id:
                fail("CONTEXT_MISMATCH", 422)
            invoice = await self.invoice(payment.parent_id)
        elif data.invoice_id:
            invoice = await self.invoice(data.invoice_id)
        else:
            invoice = None
        if invoice:
            if job_id and job_id != invoice.job_id or booking_id and booking_id != invoice.booking_id:
                fail("CONTEXT_MISMATCH", 422)
            job_id, booking_id, garage_id = invoice.job_id, invoice.booking_id, invoice.garage_id
        if job_id:
            job = await self.job(job_id)
            if booking_id and booking_id != job.booking_id:
                fail("CONTEXT_MISMATCH", 422)
            booking_id, garage_id = job.booking_id, job.garage_id
        if booking_id:
            booking, link = await self.booking(booking_id)
            if garage_id and garage_id != booking.garage_id:
                fail("CONTEXT_MISMATCH", 422)
            garage_id = booking.garage_id
        return booking_id, job_id, garage_id

    async def create_ticket(self, data):
        booking_id, job_id, garage_id = await self.validate_ticket_context(data)
        await self.validate_attachments(data.attachment_ids, "SUPPORT_ATTACHMENT")
        payload = data.model_dump()
        payload.update(booking_id=booking_id, job_id=job_id)
        row = await self.add("TICKET", payload, status="OPEN", garage_id=garage_id)
        await self.notify("SUPPORT", "Support ticket opened", row.id, f"ticket:{row.id}")
        return self.row(row)

    async def ticket_send(self, identifier, data, *, sender_role="CUSTOMER", sender_id=None):
        ticket = await self.resource(identifier, "TICKET")
        key = hashlib.sha256(f"{identifier}:{sender_role}:{sender_id or self.customer_id}:{data.client_message_id}".encode()).hexdigest()
        previous = (await self.db.execute(self.query("TICKET_MESSAGE").where(
            CustomerResource.dedupe_key == key))).scalar_one_or_none()
        if previous:
            if previous.payload["text"] != data.text or previous.payload["attachment_ids"] != [str(i) for i in data.attachment_ids]:
                fail("IDEMPOTENCY_CONFLICT", 409)
            return self.row(previous), False
        if ticket.status in {"CLOSED", "RESOLVED"}:
            fail("TICKET_READ_ONLY", 409)
        await self.validate_attachments(data.attachment_ids, "SUPPORT_ATTACHMENT")
        row = await self.add("TICKET_MESSAGE", {
            **data.model_dump(), "sender_role": sender_role, "sent_at": now(),
        }, parent_id=identifier, garage_id=ticket.garage_id, key=key)
        if sender_role != "CUSTOMER":
            await self.notify("SUPPORT", "New support reply", identifier, f"support-message:{row.id}")
        return self.row(row), True
