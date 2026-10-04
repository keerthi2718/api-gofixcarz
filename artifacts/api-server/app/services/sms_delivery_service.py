"""MSG91 report normalization and atomic, replay-safe correlation."""
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sms_delivery import SMSDelivery


REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")
# Operations troubleshooting window, independent of status/report retries.
SMS_DELIVERY_RETENTION = timedelta(days=30)
STATUS_MAP = {
    "0": ("pending", None),
    "1": ("delivered", None),
    "2": ("failed", "operator_failure"),
    "9": ("failed", "ndnc"),
    "16": ("failed", "rejected"),
    "25": ("failed", "rejected"),
    "17": ("failed", "blocked_number"),
    "20": ("failed", "country_blocked"),
}
# Exact allowlist only. Never store arbitrary provider prose, even when it
# appears benign: it can contain a phone, message text, OTP, or credentials.
SAFE_REASONS = {
    "template id not found on dlt": "dlt_template_not_found",
    "template mismatch": "dlt_template_mismatch",
    "sender id not found on dlt": "dlt_sender_not_found",
}


def normalize_report(payload: object) -> dict:
    """Parse the flat JSON contract shared by SendOTP and SMS Webhook (New).

    OTP reports document requestId and status 1/2. Retain the existing SMS
    status allowlist for compatibility; never infer failure from no callback.
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid delivery report")
    request_id = payload.get("requestId")
    status = payload.get("status")
    if (
        not isinstance(request_id, str)
        or REQUEST_ID_PATTERN.fullmatch(request_id) is None
        or type(status) not in (str, int)
        or str(status) not in STATUS_MAP
    ):
        raise HTTPException(400, "Invalid delivery report")
    normalized, category = STATUS_MAP[str(status)]
    reason = payload.get("failureReason")
    if normalized == "failed" and isinstance(reason, str):
        category = SAFE_REASONS.get(reason.strip().lower(), category)
    return {
        "request_id": request_id,
        "status": normalized,
        "failure_category": category,
    }


class SMSDeliveryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_expired(self, *, now: datetime | None = None) -> int:
        """Delete old accepted and callback-only rows; caller owns commit."""
        cutoff = (now or datetime.now(timezone.utc)) - SMS_DELIVERY_RETENTION
        result = await self.session.execute(
            delete(SMSDelivery).where(
                func.coalesce(SMSDelivery.accepted_at, SMSDelivery.created_at) < cutoff
            )
        )
        return result.rowcount

    async def register_submission(self, request_id: str) -> None:
        # Preserve any report which raced ahead of this transaction.
        stmt = insert(SMSDelivery).values(
            request_id=request_id, status="pending",
            accepted_at=datetime.now(timezone.utc),
        )
        await self.session.execute(stmt.on_conflict_do_update(
            index_elements=[SMSDelivery.request_id],
            set_={"accepted_at": stmt.excluded.accepted_at},
            where=SMSDelivery.accepted_at.is_(None),
        ))

    async def record_report(self, report: dict) -> None:
        stmt = insert(SMSDelivery).values(
            **report, reported_at=datetime.now(timezone.utc),
        )
        # Delivered wins over failed; terminal statuses cannot regress to pending.
        # Same-status retries are no-ops, preserving the first report timestamp.
        advance = and_(
            SMSDelivery.status != stmt.excluded.status,
            SMSDelivery.status != "delivered",
            (SMSDelivery.status == "pending") | (stmt.excluded.status == "delivered"),
        )
        await self.session.execute(stmt.on_conflict_do_update(
            index_elements=[SMSDelivery.request_id],
            set_={
                "status": stmt.excluded.status,
                "failure_category": stmt.excluded.failure_category,
                "reported_at": stmt.excluded.reported_at,
            },
            where=advance,
        ))

    async def diagnostic(self, request_id: str) -> dict:
        if REQUEST_ID_PATTERN.fullmatch(request_id) is None:
            raise HTTPException(404, "Submission not found")
        result = await self.session.execute(select(SMSDelivery).where(
            SMSDelivery.request_id == request_id,
            SMSDelivery.accepted_at.is_not(None),
        ))
        record = result.scalar_one_or_none()
        if record is None:
            raise HTTPException(404, "Submission not found")
        return {
            "request_id": record.request_id,
            "status": record.status,
            "failure_category": record.failure_category,
            "accepted_at": record.accepted_at.isoformat(),
            "reported_at": record.reported_at.isoformat() if record.reported_at else None,
        }