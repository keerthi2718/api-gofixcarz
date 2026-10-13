"""Money from confirmed source events only; snapshots preserve full bounded datasets."""
from collections import Counter, defaultdict
from datetime import timedelta
import uuid
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.core.admin_read_filters import AdminReadFilters, apply_admin_filters
from app.core.config import settings
from app.models.admin_operations import SourceRecord, AdminResource
from app.models.garage import Garage
from app.models.job import JobStatus
from app.models.job import Job
from app.models.user import User
from app.services.admin_operations_service import AdminOperationsService, now, record_row


class AdminMetricsService(AdminOperationsService):
    def normalized(self, filters):
        from dataclasses import replace
        from zoneinfo import ZoneInfo
        end = filters.date_to or (filters.date_from + timedelta(days=29) if filters.date_from else now().astimezone(ZoneInfo(filters.timezone)).date())
        return replace(filters, date_from=filters.date_from or end-timedelta(days=29), date_to=end)

    async def bounded(self, query):
        rows = (await self.session.execute(query.limit(settings.ADMIN_MAX_REPORT_ROWS + 1))).scalars().all()
        if len(rows) > settings.ADMIN_MAX_REPORT_ROWS:
            raise HTTPException(413, "DATASET_TOO_LARGE: narrow the filters")
        return rows

    async def dataset(self, filters, snapshot_id=None, exclude_inactive=False):
        filters = self.normalized(filters)
        metadata = jsonable_encoder(filters.metadata())
        if snapshot_id:
            snapshot = await self.resource(snapshot_id, "SNAPSHOT")
            if snapshot.payload["filters"] != metadata or snapshot.payload["exclude_inactive"] != exclude_inactive:
                raise HTTPException(409, "SNAPSHOT_FILTER_MISMATCH")
            return snapshot
        garages_query = apply_admin_filters(select(Garage).where(Garage.deleted_at.is_(None)), filters)
        if exclude_inactive:
            garages_query = garages_query.where(Garage.operational_status == "ACTIVE")
        garages = await self.bounded(garages_query)
        garage_ids = [g.id for g in garages]
        jobs = await self.bounded(self.admin.repo.jobs_query().where(
            Job.garage_id.in_(garage_ids),
            ((Job.created_at >= filters.boundary(filters.date_from)) &
             (Job.created_at < filters.boundary(filters.date_to, exclusive_end=True))) |
            ((Job.completed_at >= filters.boundary(filters.date_from)) &
             (Job.completed_at < filters.boundary(filters.date_to, exclusive_end=True))),
        ))
        # Include event-date financial/booking sources independent of job creation cohort.
        records = await self.bounded(select(SourceRecord).where(
            SourceRecord.garage_id.in_(garage_ids), SourceRecord.occurred_at <= now()).order_by(SourceRecord.id))
        from app.models.booking import Booking
        bookings = await self.bounded(self.admin.repo.bookings_query(filters=filters).where(
            Booking.garage_id.in_(garage_ids)))
        owners = (await self.session.execute(select(User).where(User.id.in_([g.user_id for g in garages])))).scalars().all()
        snapshot = AdminResource(
            id=uuid.uuid4(), kind="SNAPSHOT", status="READY",
            actor_id=uuid.UUID(self.session.info["admin_access"]["principal_id"]),
            expires_at=now()+timedelta(hours=settings.ADMIN_SNAPSHOT_HOURS),
            payload={
                "scope_signature": self.scope_signature(), "filters": metadata,
                "exclude_inactive": exclude_inactive, "generated_at": now().isoformat(),
                "garages": [{"id": str(g.id), "owner_id": str(g.user_id), "city": g.city} for g in garages],
                "owners": {str(o.id): o.name for o in owners},
                "jobs": jsonable_encoder([{
                    "id": j.id, "garage_id": j.garage_id, "job_number": j.job_number,
                    "status": j.status.value, "created_at": j.created_at, "completed_at": j.completed_at,
                } for j in jobs]),
                "records": [record_row(r) for r in records],
                "bookings": jsonable_encoder([{
                    "id": b.id, "garage_id": b.garage_id, "status": b.status.value,
                    "created_at": b.created_at, "service_requested": b.service_requested,
                } for b in bookings]),
                "definitions": {
                    "jobs": "created-in-window cohort; current status frozen at generated_at",
                    "collections": "CAPTURED payment occurred_at; amounts in integer INR paise",
                    "refunds": "SETTLED refund occurred_at; amounts in integer INR paise",
                    "invoices": "ISSUED/PAID nonvoid invoice occurred_at",
                    "conversion": "unique accepted booking event cohort, converted by snapshot time",
                    "completion": "valid completed jobs in creation cohort; weighted hours",
                },
            },
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    def in_window(self, timestamp, filters):
        if timestamp is None:
            return False
        from datetime import datetime
        stamp = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        return (not filters.date_from or stamp >= filters.boundary(filters.date_from)) and (
            not filters.date_to or stamp < filters.boundary(filters.date_to, exclusive_end=True))

    def finance(self, snapshot, filters, garage_ids=None):
        filters = self.normalized(filters)
        records = snapshot.payload["records"]
        if garage_ids is not None:
            records = [r for r in records if r["garage_id"] in garage_ids]
        records = [r for r in records if self.in_window(r["occurred_at"], filters)]
        payments = [r for r in records if r["kind"] == "PAYMENT"]
        captured = [r for r in payments if r["status"] == "CAPTURED"]
        refunds = [r for r in records if r["kind"] == "REFUND" and r["status"] == "SETTLED"]
        invoices = [r for r in records if r["kind"] == "INVOICE" and r["status"] in ("ISSUED", "PAID")]
        gross = sum(r["amount"] for r in captured)
        refunded = sum(r["amount"] for r in refunds)
        invoice_total = sum(r["total_amount"] for r in invoices)
        all_captures = defaultdict(int)
        invoice_by_id = {r["id"]: r for r in snapshot.payload["records"] if r["kind"] == "INVOICE" and r["status"] != "VOID"}
        for r in snapshot.payload["records"]:
            if r["kind"] == "PAYMENT" and r["status"] == "CAPTURED":
                all_captures[r["parent_id"]] += r["amount"]
        paid_ids = {r["parent_id"] for r in captured if r["parent_id"] in invoice_by_id and
                    all_captures[r["parent_id"]] >= invoice_by_id[r["parent_id"]]["total_amount"]}
        return {
            "gross_collected_amount": gross, "refunded_amount": refunded, "net_collected_amount": gross-refunded,
            "captured_payments": len(captured), "failed_attempts": sum(r["status"] == "FAILED" for r in payments),
            "paid_invoice_count": len(paid_ids),
            "issued_invoice_count": len(invoices), "issued_invoice_total_amount": invoice_total,
            "average_invoice_amount": invoice_total/len(invoices) if invoices else None, "currency": "INR",
            "money_unit": "paise", "source_status": "NO_RECORDS" if not records else "RECORDED_EVENTS",
        }

    def owner_rows(self, snapshot, filters):
        filters = self.normalized(filters)
        rows = []
        for owner_id, name in sorted(snapshot.payload["owners"].items()):
            garages = [g for g in snapshot.payload["garages"] if g["owner_id"] == owner_id]
            ids = {g["id"] for g in garages}
            jobs = [j for j in snapshot.payload["jobs"] if j["garage_id"] in ids and self.in_window(j["created_at"], filters)]
            events = [r for r in snapshot.payload["records"] if r["kind"] == "BOOKING_EVENT" and r["garage_id"] in ids]
            accepted = {r["booking_id"] for r in events if r["status"] == "ACCEPTED" and self.in_window(r["occurred_at"], filters)}
            converted = {r["booking_id"] for r in events if r["status"] == "CONVERTED"} & accepted
            from datetime import datetime
            durations = []
            excluded = 0
            for job in jobs:
                if job["status"] == "COMPLETED":
                    if job["completed_at"]:
                        duration = (datetime.fromisoformat(job["completed_at"]) - datetime.fromisoformat(job["created_at"])).total_seconds()/3600
                        if duration >= 0:
                            durations.append(duration)
                            continue
                    excluded += 1
            counts = {status.value: 0 for status in JobStatus}
            counts.update(Counter(j["status"] for j in jobs))
            row = {
                "owner_id": owner_id, "owner_name": name, "garage_ids": sorted(ids),
                "jobs_created": len(jobs), "status_counts": counts, "completed_jobs": counts["COMPLETED"],
                "eligible_garages": len(garages), "average_jobs_per_garage": len(jobs)/len(garages) if garages else None,
                "eligible_accepted_bookings": len(accepted), "converted_bookings": len(converted),
                "conversion_percent": 100*len(converted)/len(accepted) if accepted else None,
                "completion_sample_size": len(durations), "completion_total_hours": sum(durations),
                "average_completion_hours": sum(durations)/len(durations) if durations else None,
                "completion_exclusions": excluded,
                "garage_breakdown": [{"garage_id": g["id"], "jobs_created": sum(j["garage_id"] == g["id"] for j in jobs)} for g in garages],
            }
            row.update(self.finance(snapshot, filters, ids))
            row["missing_sources"] = ["booking_acceptance_history"] if not events else []
            rows.append(row)
        return rows

    def metadata(self, snapshot):
        return {"snapshot_id": snapshot.id, "generated_at": snapshot.payload["generated_at"],
                "expires_at": snapshot.expires_at, "filters": snapshot.payload["filters"],
                "metric_definitions": snapshot.payload["definitions"]}

    def totals(self, rows):
        keys = ("jobs_created", "eligible_garages", "eligible_accepted_bookings", "converted_bookings",
                "completion_sample_size", "completion_total_hours", "completion_exclusions",
                "gross_collected_amount", "refunded_amount", "net_collected_amount", "paid_invoice_count",
                "issued_invoice_count", "issued_invoice_total_amount", "failed_attempts")
        totals = {key: sum(r[key] for r in rows) for key in keys}
        totals["status_counts"] = {s.value: sum(r["status_counts"][s.value] for r in rows) for s in JobStatus}
        for name, numerator, denominator, multiplier in [
            ("average_jobs_per_garage", "jobs_created", "eligible_garages", 1),
            ("conversion_percent", "converted_bookings", "eligible_accepted_bookings", 100),
            ("average_completion_hours", "completion_total_hours", "completion_sample_size", 1),
            ("average_invoice_amount", "issued_invoice_total_amount", "issued_invoice_count", 1),
        ]:
            totals[name] = multiplier*totals[numerator]/totals[denominator] if totals[denominator] else None
        return totals

    def trends(self, snapshot, filters, period, owner_id=None, finance=False):
        filters = self.normalized(filters)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        if period not in ("daily", "weekly", "monthly"):
            raise HTTPException(422, "PERIOD_INVALID")
        ids = {g["id"] for g in snapshot.payload["garages"] if not owner_id or g["owner_id"] == str(owner_id)}
        buckets = defaultdict(lambda: {"jobs_created": 0, "jobs_completed": 0, "gross_collected_amount": 0, "refunded_amount": 0})

        def bucket(stamp):
            day = datetime.fromisoformat(stamp).astimezone(ZoneInfo(filters.timezone)).date()
            if period == "weekly":
                day -= timedelta(days=day.weekday())
            elif period == "monthly":
                day = day.replace(day=1)
            return day.isoformat()
        if not finance:
            for job in snapshot.payload["jobs"]:
                if job["garage_id"] not in ids:
                    continue
                if self.in_window(job["created_at"], filters):
                    buckets[bucket(job["created_at"])]["jobs_created"] += 1
                if self.in_window(job["completed_at"], filters):
                    buckets[bucket(job["completed_at"])]["jobs_completed"] += 1
        for r in snapshot.payload["records"]:
            if r["garage_id"] in ids and self.in_window(r["occurred_at"], filters):
                if r["kind"] == "PAYMENT" and r["status"] == "CAPTURED":
                    buckets[bucket(r["occurred_at"])]["gross_collected_amount"] += r["amount"]
                elif r["kind"] == "REFUND" and r["status"] == "SETTLED":
                    buckets[bucket(r["occurred_at"])]["refunded_amount"] += r["amount"]
        return [{"date": day, **value, "net_collected_amount": value["gross_collected_amount"]-value["refunded_amount"]}
                for day, value in sorted(buckets.items())]
