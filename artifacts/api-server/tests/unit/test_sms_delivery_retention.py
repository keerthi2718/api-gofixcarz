"""Retention tests use an isolated temporary Postgres table; no SMS is sent."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
import pytest
from sqlalchemy import MetaData, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from app.database.session import _connect_args, _db_url
from app.models.sms_delivery import SMSDelivery
from app.services.sms_delivery_service import (
    SMS_DELIVERY_RETENTION, SMSDeliveryService, normalize_report,
)


@pytest.fixture
async def delivery_session():
    engine = create_async_engine(_db_url, connect_args=_connect_args, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            table = SMSDelivery.__table__.to_metadata(MetaData())
            table._prefixes = ["TEMPORARY"]
            await connection.execute(CreateTable(table))
            for index in table.indexes:
                await connection.execute(CreateIndex(index))
            async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                yield session
            await connection.exec_driver_sql("DROP TABLE pg_temp.sms_deliveries")
    finally:
        await engine.dispose()


@pytest.mark.parametrize("status", ["pending", "delivered", "failed"])
async def test_cleanup_strict_boundary_for_accepted_and_callback_only(delivery_session, status):
    now = datetime.now(timezone.utc)
    cutoff = now - SMS_DELIVERY_RETENTION
    records = []
    expected = set()
    for accepted in (True, False):
        for label, delta in (
            ("old", -timedelta(microseconds=1)),
            ("boundary", timedelta()),
            ("recent", timedelta(microseconds=1)),
        ):
            request_id = f"retention_{accepted}_{label}_{status}"
            anchor = cutoff + delta
            records.append({
                "request_id": request_id, "status": status,
                "accepted_at": anchor if accepted else None,
                # An early callback may be much older than acceptance.
                "created_at": anchor - timedelta(days=10) if accepted else anchor,
                # A report just received must not rescue an expired row.
                "reported_at": now,
            })
            if label != "old":
                expected.add(request_id)
    await delivery_session.execute(insert(SMSDelivery), records)
    service = SMSDeliveryService(delivery_session)
    assert await service.delete_expired(now=now) == 2
    assert set((await delivery_session.scalars(select(SMSDelivery.request_id))).all()) == expected
    assert await service.delete_expired(now=now) == 0


async def test_delayed_final_report_survives_until_acceptance_window_expires(delivery_session):
    now = datetime.now(timezone.utc)
    accepted = now - timedelta(days=29)
    request_id = "delayed_final_report_1234"
    await delivery_session.execute(insert(SMSDelivery).values(
        request_id=request_id, status="pending", accepted_at=accepted,
        created_at=accepted,
    ))
    service = SMSDeliveryService(delivery_session)
    assert await service.delete_expired(now=now) == 0
    report = normalize_report({"requestId": request_id, "status": "1"})
    await service.record_report(report)
    original = await service.diagnostic(request_id)
    assert original["status"] == "delivered"
    await service.record_report(report)
    assert await service.diagnostic(request_id) == original
    assert await service.delete_expired(now=accepted + SMS_DELIVERY_RETENTION) == 0
    assert await service.delete_expired(
        now=accepted + SMS_DELIVERY_RETENTION + timedelta(microseconds=1)
    ) == 1
    with pytest.raises(HTTPException) as exc:
        await service.diagnostic(request_id)
    assert exc.value.status_code == 404


async def test_early_report_gets_full_window_when_submission_matches(delivery_session):
    now = datetime.now(timezone.utc)
    request_id = "early_report_submission_1234"
    await delivery_session.execute(insert(SMSDelivery).values(
        request_id=request_id, status="delivered", accepted_at=None,
        created_at=now - timedelta(days=29), reported_at=now - timedelta(days=29),
    ))
    service = SMSDeliveryService(delivery_session)
    await service.register_submission(request_id)
    original = await service.diagnostic(request_id)
    assert original["status"] == "delivered"
    assert await service.delete_expired(now=now + timedelta(days=2)) == 0
    await service.register_submission(request_id)
    assert await service.diagnostic(request_id) == original


async def test_callback_after_deletion_is_hidden_and_eventually_removed(delivery_session):
    now = datetime.now(timezone.utc)
    request_id = "expired_callback_submission_1234"
    await delivery_session.execute(insert(SMSDelivery).values(
        request_id=request_id, status="pending",
        accepted_at=now - timedelta(days=31), created_at=now - timedelta(days=31),
    ))
    service = SMSDeliveryService(delivery_session)
    assert await service.delete_expired(now=now) == 1
    report = normalize_report({"requestId": request_id, "status": "1"})
    await service.record_report(report)
    await service.record_report(report)
    with pytest.raises(HTTPException) as exc:
        await service.diagnostic(request_id)
    assert exc.value.status_code == 404
    assert await service.delete_expired(now=now) == 0
    assert await service.delete_expired(now=now + timedelta(days=31)) == 1


async def test_cleanup_job_commits_and_logs_count(monkeypatch):
    from app import main
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(main, "async_session", Mock(return_value=context))
    cleanup = AsyncMock(return_value=7)
    monkeypatch.setattr(SMSDeliveryService, "delete_expired", cleanup)
    logger = Mock()
    monkeypatch.setattr(main, "logger", logger)
    await main._delete_expired_sms_deliveries()
    cleanup.assert_awaited_once()
    session.commit.assert_awaited_once()
    logger.info.assert_called_once_with("SMS delivery cleanup: 7 row(s) deleted")


async def test_cleanup_failure_is_logged_without_commit(monkeypatch):
    from app import main
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(main, "async_session", Mock(return_value=context))
    monkeypatch.setattr(SMSDeliveryService, "delete_expired", AsyncMock(
        side_effect=RuntimeError("database unavailable"),
    ))
    logger = Mock()
    monkeypatch.setattr(main, "logger", logger)
    await main._delete_expired_sms_deliveries()
    session.commit.assert_not_awaited()
    assert context.__aexit__.call_args.args[0] is RuntimeError
    logger.exception.assert_called_once_with("SMS delivery cleanup failed")


async def test_lifespan_registers_daily_cleanup_and_runs_it_at_startup(monkeypatch):
    from app import main
    scheduler = Mock()
    monkeypatch.setattr(main, "AsyncIOScheduler", Mock(return_value=scheduler))
    sms_cleanup = AsyncMock()
    monkeypatch.setattr(main, "_delete_expired_sms_deliveries", sms_cleanup)
    monkeypatch.setattr(main, "_delete_expired_refresh_tokens", AsyncMock())
    dispose = AsyncMock()
    monkeypatch.setattr(main, "engine", Mock(dispose=dispose))
    async with main.lifespan(main.app):
        scheduler.add_job.assert_any_call(
            sms_cleanup, trigger="interval", hours=24,
            id="delete_expired_sms_deliveries", replace_existing=True,
            max_instances=1, misfire_grace_time=3600,
        )
        scheduler.start.assert_called_once()
        sms_cleanup.assert_awaited_once()
    scheduler.shutdown.assert_called_once_with(wait=False)
    dispose.assert_awaited_once()