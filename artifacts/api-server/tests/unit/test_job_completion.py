"""Completion billing regressions with mocked database I/O; no live data changes."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.job import Job, JobStatus
from app.schemas.job import JobCompleteUpdate, JobStatusUpdate
from app.services.job_service import JobService


def make_service(status, services=None, labour=None):
    now = datetime.now(timezone.utc)
    job = Job(
        id=uuid4(),
        garage_id=uuid4(),
        job_number="JC-001",
        status=status,
        services=services,
        labour=labour,
        estimated_amount=Decimal("9999.00"),
        created_at=now,
        updated_at=now,
    )
    session = SimpleNamespace(
        add=Mock(), flush=AsyncMock(), refresh=AsyncMock(),
    )
    service = JobService(session)
    service.repo.get_by_id = AsyncMock(return_value=job)
    return service, job, session


COMPLETION_PATHS = [
    ("status", JobStatus.IN_PROGRESS),
    ("status", JobStatus.QUALITY_CHECK),
    ("status", JobStatus.READY),
    ("complete", JobStatus.OPEN),
    ("complete", JobStatus.IN_PROGRESS),
    ("complete", JobStatus.WAITING_FOR_PARTS),
    ("complete", JobStatus.QUALITY_CHECK),
    ("complete", JobStatus.READY),
]


@pytest.mark.parametrize("path,start_status", COMPLETION_PATHS)
@pytest.mark.parametrize("services,labour,expected", [
    (
        [{"name": "Parts", "price": "1000.00", "qty": 2},
         {"name": "Service", "price": "250.00", "qty": 1}],
        {"charge": "500.00"},
        {
            "services_total": "2250.00", "labour_total": "500.00",
            "subtotal": "2750.00", "gst_amount": "495.00",
            "grand_total": "3245.00",
        },
    ),
    (
        [{"name": "Fractional item", "price": "0.10", "qty": 3}],
        {"charge": "0.20"},
        {
            "services_total": "0.30", "labour_total": "0.20",
            "subtotal": "0.50", "gst_amount": "0.09",
            "grand_total": "0.59",
        },
    ),
    (
        None, None,
        {
            "services_total": "0.00", "labour_total": "0.00",
            "subtotal": "0.00", "gst_amount": "0.00",
            "grand_total": "0.00",
        },
    ),
])
async def test_both_completion_paths_save_billing(
    path, start_status, services, labour, expected,
):
    service, job, session = make_service(start_status, services, labour)
    notes = "Work finished"

    if path == "status":
        result = await service.change_status(
            job.garage_id, job.id,
            JobStatusUpdate(status=JobStatus.COMPLETED, notes=notes),
        )
    else:
        result = await service.complete(
            job.garage_id, job.id, JobCompleteUpdate(notes=notes),
        )

    assert job.status == result.status == JobStatus.COMPLETED
    assert job.billing == expected
    assert Decimal(str(job.final_amount)) == Decimal(expected["grand_total"])
    assert result.final_amount == Decimal(expected["grand_total"])
    assert result.billing.grand_total == Decimal(expected["grand_total"])
    assert job.completed_at is not None
    assert job.completed_at.tzinfo is not None
    assert job.updated_at == job.completed_at == result.completed_at
    # Exactly one completion event, preserving supplied notes.
    session.add.assert_called_once()
    timeline = session.add.call_args.args[0]
    assert timeline.job_id == job.id
    assert timeline.status == "COMPLETED"
    assert timeline.notes == notes
    session.refresh.assert_awaited_once_with(job)
    service.repo.get_by_id.assert_awaited_once_with(job.id, job.garage_id)


@pytest.mark.parametrize("start_status", [
    JobStatus.OPEN, JobStatus.WAITING_FOR_PARTS,
    JobStatus.COMPLETED, JobStatus.CANCELLED,
])
async def test_status_completion_keeps_transition_guards(start_status):
    service, job, session = make_service(start_status)
    with pytest.raises(BadRequestException):
        await service.change_status(
            job.garage_id, job.id, JobStatusUpdate(status=JobStatus.COMPLETED),
        )
    session.flush.assert_not_awaited()
    session.add.assert_not_called()
    assert job.status == start_status
    assert job.billing is None
    assert job.final_amount is None


@pytest.mark.parametrize("start_status", [
    JobStatus.COMPLETED, JobStatus.CANCELLED,
])
async def test_complete_endpoint_keeps_terminal_guards(start_status):
    service, job, session = make_service(start_status)
    with pytest.raises(BadRequestException):
        await service.complete(job.garage_id, job.id, JobCompleteUpdate())
    session.flush.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.parametrize("new_status", [
    JobStatus.IN_PROGRESS, JobStatus.CANCELLED,
])
async def test_non_completion_status_does_not_generate_billing(new_status):
    service, job, session = make_service(
        JobStatus.OPEN, [{"price": "1000.00", "qty": 1}], {"charge": "500.00"},
    )
    result = await service.change_status(
        job.garage_id, job.id, JobStatusUpdate(status=new_status, notes="Status update"),
    )
    assert job.status == result.status == new_status
    assert job.final_amount is None
    assert job.billing is None
    assert job.completed_at is None
    session.add.assert_called_once()


async def test_completion_defaults_timeline_notes():
    service, job, session = make_service(JobStatus.READY)
    await service.change_status(
        job.garage_id, job.id, JobStatusUpdate(status=JobStatus.COMPLETED),
    )
    assert session.add.call_args.args[0].notes == "Job completed"


async def test_missing_job_cannot_be_completed():
    service, job, session = make_service(JobStatus.READY)
    service.repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await service.change_status(
            job.garage_id, job.id, JobStatusUpdate(status=JobStatus.COMPLETED),
        )
    session.flush.assert_not_awaited()


async def test_database_failure_is_not_reported_as_completion_success():
    service, job, session = make_service(JobStatus.READY)
    session.flush.side_effect = RuntimeError("Database write failed")
    with pytest.raises(RuntimeError, match="Database write failed"):
        await service.change_status(
            job.garage_id, job.id, JobStatusUpdate(status=JobStatus.COMPLETED),
        )
    session.add.assert_not_called()
    session.refresh.assert_not_awaited()
