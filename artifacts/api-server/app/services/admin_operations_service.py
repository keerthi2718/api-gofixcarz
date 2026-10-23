import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.admin_policy import resolve_permissions, require_permission, scope_ids
from app.core.config import settings
from app.core.admin_read_filters import apply_admin_filters
from app.models.admin_account import AdminAccount
from app.models.admin_operations import CustomerAccount, AccountGarage, SourceRecord, SupportMessage, AdminResource
from app.models.garage import Garage
from app.models.job import Job, JobStatus
from app.models.notification import Notification
from app.models.user import User
from app.services.admin_service import AdminService

FINANCIAL = {"INVOICE", "PAYMENT", "REFUND", "DISPUTE"}


def now():
    return datetime.now(timezone.utc)


def fingerprint(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record_row(record):
    result = {key: getattr(record, key) for key in (
        "id", "kind", "garage_id", "customer_id", "booking_id", "job_id", "parent_id",
        "status", "occurred_at", "version", "currency",
    )}
    result.update(record.payload)
    if record.kind in FINANCIAL:
        result["total_amount" if record.kind == "INVOICE" else "amount"] = record.amount
    return jsonable_encoder(result)


class AdminOperationsService:
    def __init__(self, session):
        self.session = session
        self.admin = AdminService(session)

    async def audit(self, action, resource_id=None, details=None):
        access = self.session.info["admin_access"]
        await self.admin.audit(uuid.UUID(access["principal_id"]), action, resource_id, details)

    async def paged(self, query, page=1, page_size=20, serialize=record_row):
        rows, total = await self.admin.repo.page(query, page, page_size)
        return {"items": [serialize(row) for row in rows], "total": total, "page": page,
                "page_size": page_size, "pages": max(1, (total + page_size - 1)//page_size)}

    def records_query(self, kind, filters=None, status=None, customer_id=None, parent_id=None):
        query = select(SourceRecord).join(Garage, Garage.id == SourceRecord.garage_id).where(
            SourceRecord.kind == kind, Garage.deleted_at.is_(None))
        query = apply_admin_filters(query, filters, SourceRecord.occurred_at)
        for column, value in ((SourceRecord.status, status), (SourceRecord.customer_id, customer_id),
                              (SourceRecord.parent_id, parent_id)):
            if value is not None:
                query = query.where(column == value)
        return query.order_by(SourceRecord.occurred_at.desc(), SourceRecord.id)

    async def record(self, record_id, kind, lock=False):
        query = self.records_query(kind).where(SourceRecord.id == record_id)
        if lock:
            query = query.with_for_update(of=SourceRecord).execution_options(populate_existing=True)
        record = (await self.session.execute(query)).scalar_one_or_none()
        if not record:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        return record

    async def customer(self, account_id):
        account = (await self.session.execute(select(CustomerAccount).where(
            CustomerAccount.id == account_id))).scalar_one_or_none()
        if not account:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        return account

    async def customer_row(self, account):
        finance = "finance.read" in self.session.info["admin_access"]["permissions"]
        garage_ids = (await self.session.execute(select(AccountGarage.garage_id).where(
            AccountGarage.account_id == account.id))).scalars().all()
        support = (await self.session.execute(select(func.count()).select_from(SourceRecord).where(
            SourceRecord.customer_id == account.id, SourceRecord.kind == "TICKET",
            SourceRecord.status.notin_(["CLOSED", "RESOLVED"])))).scalar_one()
        failed = None
        if finance:
            failed = bool((await self.session.execute(select(func.count()).select_from(SourceRecord).where(
                SourceRecord.customer_id == account.id, SourceRecord.kind == "PAYMENT",
                SourceRecord.status == "FAILED"))).scalar_one())
        return jsonable_encoder({
            "id": account.id, "name": account.name, "email": account.email, "mobile": account.mobile,
            "account_status": account.account_status, "last_activity_at": account.last_activity_at,
            "garage_ids": garage_ids, "has_support_flags": bool(support), "has_failed_payments": failed,
            "source": account.source, "restricted_fields": [] if finance else ["has_failed_payments"],
        })

    async def mutate_garage(self, garage_id, data, verification=False):
        garage = (await self.session.execute(select(Garage).where(
            Garage.id == garage_id, Garage.deleted_at.is_(None),
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not garage:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        if garage.admin_version != data.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        column = "verification_status" if verification else "operational_status"
        before = getattr(garage, column)
        setattr(garage, column, getattr(data, column))
        garage.admin_version += 1
        await self.audit("garage." + column + ".write", garage.id, {
            "before": before, "after": getattr(garage, column), "reason": data.reason,
            "version": garage.admin_version,
        })
        return {"id": garage.id, "operational_status": garage.operational_status,
                "verification_status": garage.verification_status, "version": garage.admin_version,
                "new_work_allowed": garage.operational_status == "ACTIVE"}

    async def delays(self, filters=None, status=None, overdue=None):
        query = self.admin.repo.jobs_query(filters=filters).where(
            Job.status.notin_([JobStatus.COMPLETED, JobStatus.CANCELLED]))
        if status:
            query = query.where(Job.status == status)
        jobs = (await self.session.execute(query.options(selectinload(Job.timelines)).limit(
            settings.ADMIN_MAX_REPORT_ROWS + 1))).scalars().all()
        if len(jobs) > settings.ADMIN_MAX_REPORT_ROWS:
            raise HTTPException(413, "RESULT_TOO_LARGE")
        stamp = now()
        items = []
        for job in jobs:
            entries = [t.created_at for t in job.timelines if t.status == job.status and t.created_at <= stamp]
            state_entered = max(entries) if entries else job.created_at
            hours = max(0, (stamp - state_entered).total_seconds()/3600)
            is_overdue = hours >= settings.ADMIN_DELAY_HOURS
            if overdue is not None and is_overdue != overdue:
                continue
            items.append({
                "job_id": job.id, "job_number": job.job_number, "garage_id": job.garage_id,
                "status": job.status.value, "state_entered_at": state_entered,
                "state_age_hours": round(hours, 4), "threshold_hours": settings.ADMIN_DELAY_HOURS,
                "overdue": is_overdue, "as_of": stamp,
                "duration_basis": "latest recorded entry to current state; creation fallback",
            })
        items.sort(key=lambda item: (-item["state_age_hours"], str(item["job_id"])))
        return jsonable_encoder(items), stamp

    async def ticket_change(self, ticket_id, data, operation):
        ticket = await self.record(ticket_id, "TICKET", lock=True)
        if ticket.version != data.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        payload = dict(ticket.payload)
        before = record_row(ticket)
        if operation == "assignment":
            if data.assignee_id:
                account = await self.session.get(AdminAccount, data.assignee_id)
                if not account or not account.is_active or "support.reply" not in await resolve_permissions(self.session, account):
                    raise HTTPException(422, "ASSIGNEE_INVALID")
                if account.garage_scope is not None and str(ticket.garage_id) not in account.garage_scope:
                    raise HTTPException(422, "ASSIGNEE_SCOPE_DENIED")
            payload["assignee_id"] = str(data.assignee_id) if data.assignee_id else None
        elif operation == "priority":
            payload["priority"] = data.priority
        else:
            transitions = {
                "OPEN": {"IN_PROGRESS", "WAITING_FOR_CUSTOMER", "RESOLVED"},
                "IN_PROGRESS": {"WAITING_FOR_CUSTOMER", "RESOLVED"},
                "WAITING_FOR_CUSTOMER": {"IN_PROGRESS", "RESOLVED"},
                "RESOLVED": {"IN_PROGRESS", "CLOSED"}, "CLOSED": set(),
            }
            if data.status not in transitions[ticket.status]:
                raise HTTPException(409, "STATUS_TRANSITION_INVALID")
            ticket.status = data.status
            if data.resolution:
                payload["resolution"] = data.resolution
            if data.status == "CLOSED":
                payload["closed_at"] = now().isoformat()
        ticket.payload = payload
        ticket.version += 1
        await self.audit("support." + operation, ticket.id, {
            "before": before, "after": record_row(ticket), "reason": getattr(data, "reason", None),
        })
        return record_row(ticket)

    async def reply(self, ticket_id, data):
        ticket = await self.record(ticket_id, "TICKET", lock=True)
        actor = uuid.UUID(self.session.info["admin_access"]["principal_id"])
        existing = (await self.session.execute(select(SupportMessage).where(
            SupportMessage.ticket_id == ticket.id, SupportMessage.sender_id == actor,
            SupportMessage.client_message_id == data.client_message_id))).scalar_one_or_none()
        if existing:
            if existing.text != data.text:
                raise HTTPException(409, "MESSAGE_ID_CONFLICT")
            return message_row(existing)
        if ticket.status == "CLOSED":
            raise HTTPException(409, "TICKET_CLOSED")
        message = SupportMessage(id=uuid.uuid4(), ticket_id=ticket.id, sender_id=actor,
                                 sender_role="ADMIN", client_message_id=data.client_message_id, text=data.text)
        self.session.add(message)
        # The garage participant sees the reply through their existing notification inbox.
        self.session.add(Notification(garage_id=ticket.garage_id, title="Support reply",
                                      message=data.text, type="SUPPORT_REPLY", reference_id=ticket.id))
        await self.session.flush()
        await self.audit("support.reply", ticket.id, {"message_id": str(message.id)})
        return message_row(message)

    def scope_signature(self):
        access = self.session.info["admin_access"]
        return fingerprint({"permissions": sorted(access["permissions"]),
                            "garages": sorted(map(str, access["garage_ids"])) if access["garage_ids"] is not None else None})

    async def resource(self, resource_id, kind, lock=False):
        query = select(AdminResource).where(AdminResource.id == resource_id, AdminResource.kind == kind)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        resource = (await self.session.execute(query)).scalar_one_or_none()
        access = self.session.info["admin_access"]
        if not resource or str(resource.actor_id) != access["principal_id"]:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        if resource.expires_at <= now():
            raise HTTPException(409 if kind in ("SNAPSHOT", "PREVIEW") else 410, kind + "_EXPIRED")
        if resource.payload.get("scope_signature") != self.scope_signature():
            raise HTTPException(403, "RESOURCE_SCOPE_CHANGED")
        return resource

    async def idempotent(self, kind, key, value):
        actor = uuid.UUID(self.session.info["admin_access"]["principal_id"])
        # Serialize same-actor requests, including insertion before a resource exists.
        await self.session.execute(select(AdminAccount.id).where(AdminAccount.id == actor).with_for_update())
        resource = (await self.session.execute(select(AdminResource).where(
            AdminResource.actor_id == actor, AdminResource.kind == kind,
            AdminResource.idempotency_key == key))).scalar_one_or_none()
        if resource and resource.fingerprint != fingerprint(value):
            raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
        if resource and resource.payload.get("scope_signature") != self.scope_signature():
            raise HTTPException(403, "RESOURCE_SCOPE_CHANGED")
        return resource

    async def preview(self, data):
        if set(data.channels) != {"IN_APP"}:
            raise HTTPException(409, "CHANNEL_NOT_CONFIGURED: development announcements support IN_APP only")
        garages = select(Garage).join(User, User.id == Garage.user_id).where(
            Garage.deleted_at.is_(None), User.is_active.is_(True), User.deleted_at.is_(None))
        if data.audience.garage_ids:
            allowed = scope_ids(self.session)
            if allowed is not None and not set(data.audience.garage_ids).issubset(set(allowed)):
                raise HTTPException(403, "AUDIENCE_SCOPE_DENIED")
            garages = garages.where(Garage.id.in_(data.audience.garage_ids))
        if data.audience.city:
            garages = garages.where(Garage.city.ilike(data.audience.city))
        if data.audience.operational_status:
            garages = garages.where(Garage.operational_status == data.audience.operational_status)
        rows = (await self.session.execute(garages.order_by(Garage.id).limit(1001))).scalars().all()
        if len(rows) > 1000:
            raise HTTPException(413, "AUDIENCE_TOO_LARGE")
        resource = AdminResource(
            id=uuid.uuid4(), kind="PREVIEW", status="READY",
            actor_id=uuid.UUID(self.session.info["admin_access"]["principal_id"]), expires_at=now()+timedelta(minutes=5),
            payload={"scope_signature": self.scope_signature(), "request": data.model_dump(mode="json"),
                     "recipients": [{"garage_id": str(g.id), "recipient_id": str(g.user_id)} for g in rows]},
        )
        self.session.add(resource)
        await self.audit("announcement.preview", resource.id, {"recipient_count": len(rows)})
        return {"preview_id": resource.id, "recipient_count": len({g.user_id for g in rows}),
                "delivery_count": len(rows), "channels": ["IN_APP"], "expires_at": resource.expires_at}

    async def send(self, data, key):
        previous = await self.idempotent("ANNOUNCEMENT", key, data.model_dump(mode="json"))
        if previous:
            return announcement_row(previous)
        preview = await self.resource(data.preview_id, "PREVIEW", lock=True)
        if preview.status != "READY":
            raise HTTPException(409, "PREVIEW_ALREADY_USED")
        recipients = preview.payload["recipients"]
        # Reject changed eligibility rather than silently sending a partial audience.
        ids = [uuid.UUID(r["garage_id"]) for r in recipients]
        eligible = (await self.session.execute(select(Garage.id).join(User).where(
            Garage.id.in_(ids), Garage.deleted_at.is_(None), User.is_active.is_(True),
            User.deleted_at.is_(None)))).scalars().all()
        if set(eligible) != set(ids):
            raise HTTPException(409, "AUDIENCE_CHANGED")
        announcement = AdminResource(
            id=uuid.uuid4(), kind="ANNOUNCEMENT", actor_id=preview.actor_id, status="DELIVERED",
            idempotency_key=key, fingerprint=fingerprint(data.model_dump(mode="json")),
            expires_at=now()+timedelta(days=30),
            payload={"scope_signature": self.scope_signature(), "title": preview.payload["request"]["title"],
                     "message": preview.payload["request"]["body"],
                     "audience": preview.payload["request"], "deliveries": [
                         {**recipient, "channel": "IN_APP", "status": "DELIVERED"} for recipient in recipients]},
        )
        self.session.add(announcement)
        for recipient in recipients:
            self.session.add(Notification(garage_id=uuid.UUID(recipient["garage_id"]),
                                          title=preview.payload["request"]["title"],
                                          message=preview.payload["request"]["body"], type="ANNOUNCEMENT", reference_id=announcement.id))
        preview.status = "CONSUMED"
        await self.audit("announcement.send", announcement.id, {"delivery_count": len(recipients), "channel": "IN_APP", "reason": data.reason})
        await self.session.flush()
        return announcement_row(announcement)


def announcement_row(resource):
    return {"id": resource.id, "status": resource.status, "title": resource.payload["title"],
            "message": resource.payload["message"], "delivery_count": len(resource.payload["deliveries"]),
            "created_at": resource.created_at}


def message_row(message):
    return {"id": message.id, "sender_role": message.sender_role, "text": message.text,
            "created_at": message.created_at, "client_message_id": message.client_message_id}
