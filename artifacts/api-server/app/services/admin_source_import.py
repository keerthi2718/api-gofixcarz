"""Atomic, validated trusted-source ingestion; intentionally not a public admin write API."""
from sqlalchemy import select, text
from app.models.admin_operations import CustomerAccount, AccountGarage, SourceRecord
from app.models.garage import Garage
from app.models.booking import Booking
from app.models.job import Job


async def import_sources(session, batch):
    # Concurrent import processes must not both validate captures/refunds against stale totals.
    await session.execute(text("SELECT pg_advisory_xact_lock(138008)"))
    for data in batch.accounts:
        garages = (await session.execute(select(Garage.id).where(
            Garage.id.in_(data.garage_ids), Garage.deleted_at.is_(None)))).scalars().all()
        if len(set(garages)) != len(data.garage_ids):
            raise ValueError("Unknown or duplicate account garage")
        existing = await session.get(CustomerAccount, data.id)
        if existing:
            raise ValueError("Account source already exists; update ingestion requires source version policy")
        session.add(CustomerAccount(**data.model_dump(exclude={"garage_ids"})))
        await session.flush()
        session.add_all([AccountGarage(account_id=data.id, garage_id=garage_id) for garage_id in data.garage_ids])
    await session.flush()
    for data in batch.records:
        if await session.get(SourceRecord, data.id):
            raise ValueError("Duplicate source record ID")
        garage = await session.get(Garage, data.garage_id)
        if not garage or garage.deleted_at:
            raise ValueError("Unknown source garage")
        if data.customer_id:
            link = await session.get(AccountGarage, (data.customer_id, data.garage_id))
            if not link:
                raise ValueError("Customer account is not linked to source garage")
        for model, value in ((Booking, data.booking_id), (Job, data.job_id)):
            if value:
                linked = await session.get(model, value)
                if not linked or linked.deleted_at or linked.garage_id != data.garage_id:
                    raise ValueError("Cross-garage or missing source relationship")
        if data.parent_id:
            parent = await session.get(SourceRecord, data.parent_id)
            expected = {"PAYMENT": "INVOICE", "REFUND": "PAYMENT", "DISPUTE": "PAYMENT"}.get(data.kind)
            if not parent or parent.garage_id != data.garage_id or (expected and parent.kind != expected):
                raise ValueError("Invalid parent source relationship")
            if data.customer_id != parent.customer_id:
                raise ValueError("Cross-customer financial relationship")
            if (data.job_id and parent.job_id and data.job_id != parent.job_id) or (
                data.booking_id and parent.booking_id and data.booking_id != parent.booking_id):
                raise ValueError("Conflicting parent service relationship")
            data = data.model_copy(update={
                "job_id": data.job_id or parent.job_id, "booking_id": data.booking_id or parent.booking_id,
            })
            if data.kind == "PAYMENT" and data.status == "CAPTURED":
                captured = (await session.execute(select(SourceRecord.amount).where(
                    SourceRecord.kind == "PAYMENT", SourceRecord.parent_id == parent.id,
                    SourceRecord.status == "CAPTURED"))).scalars().all()
                if sum(captured) + data.amount > parent.amount:
                    raise ValueError("Captures exceed invoice amount")
            if data.kind == "REFUND":
                if parent.status != "CAPTURED":
                    raise ValueError("Refund requires captured payment")
                settled = (await session.execute(select(SourceRecord.amount).where(
                    SourceRecord.kind == "REFUND", SourceRecord.parent_id == parent.id,
                    SourceRecord.status == "SETTLED"))).scalars().all()
                if sum(settled) + (data.amount if data.status == "SETTLED" else 0) > parent.amount:
                    raise ValueError("Refunds exceed captured payment")
        session.add(SourceRecord(**data.model_dump()))
        await session.flush()
    return {"accounts": len(batch.accounts), "records": len(batch.records)}
