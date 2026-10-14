"""Persist in-app events for explicitly linked customer work; no push dependency."""
from app.models.customer_workspace import CustomerBookingLink
from app.services.customer_workspace_base import CustomerWorkspaceBase


async def customer_job_event(session, job):
    if not job.booking_id:
        return
    link = await session.get(CustomerBookingLink, job.booking_id)
    if link:
        svc = CustomerWorkspaceBase(session, link.customer_id)
        await svc.notify("JOBS", f"Job status: {job.status.value}", job.id,
                         f"job:{job.id}:{job.status.value}")
