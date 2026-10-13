"""Real SQL read APIs; isolated fixture rows always roll back and never send SMS."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.admin_audit_log import AdminAuditLog
from app.models.booking import BookingStatus
from app.models.garage import Garage
from app.models.job import Job
from app.models.job_timeline import JobTimeline
from app.models.user import User
from tests.integration.test_admin import headers, setup_admin_api  # noqa: F401


BASE = "/api/v1/admin"


async def test_all_monitoring_routes_are_admin_only(setup_admin_api):
    d = setup_admin_api
    for path in [
        "/garage-owners", f"/garage-owners/{d['owner'].id}",
        "/bookings/exception-statistics", f"/bookings/{d['booking'].id}",
        f"/jobs/{d['ready'].id}/timeline", f"/audit-logs/{uuid4()}",
        "/activity", f"/activity/service-funnels/{d['booking'].id}",
    ]:
        for auth, expected in [({}, 401), (headers(d["owner"]), 403)]:
            response = await d["client"].get(BASE+path, headers=auth)
            assert response.status_code == expected, (path, response.text)


async def test_owner_aggregates_and_multiple_garages_without_fake_finance(setup_admin_api):
    d = setup_admin_api
    label = f"Phase owner {uuid4()}"
    d["owner"].name = d["admin"].name = label
    extra = Garage(id=uuid4(), user_id=d["owner"].id, name=label, owner=label, city="Hyderabad")
    d["garage"].city = "Hyderabad"
    d["other_garage"].city = "Pune"
    d["session"].add(extra)
    await d["session"].flush()
    result = await d["client"].get(BASE+"/garage-owners", headers=headers(d["admin"]),
                                  params={"search": label, "page_size": 1})
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["total"] == 1
    owner = data["items"][0]
    assert owner["id"] == str(d["owner"].id)
    assert set(owner["garage_ids"]) == {str(extra.id), str(d["garage"].id)}
    assert owner["bookings"] == 1 and owner["jobs_created"] == 2
    assert owner["completed_jobs"] == 1 and owner["completed_job_amount_paise"] == 11800
    assert owner["average_rating"] is None
    assert "net_collected_amount" not in owner
    assert "otp" not in owner and "token_hash" not in owner
    assert data["filters"]["timezone"] == "UTC"
    detail = await d["client"].get(BASE+f"/garage-owners/{d['owner'].id}", headers=headers(d["admin"]))
    assert detail.status_code == 200
    assert len(detail.json()["data"]["garages"]) == 2
    not_owner = await d["client"].get(BASE+f"/garage-owners/{d['admin'].id}", headers=headers(d["admin"]))
    assert not_owner.status_code == 404
    filtered = await d["client"].get(BASE+"/garage-owners", headers=headers(d["admin"]),
                                    params={"garage_id": str(extra.id), "city": "hyderabad"})
    assert filtered.status_code == 200
    assert filtered.json()["data"]["items"][0]["garage_ids"] == [str(extra.id)]


async def test_zero_activity_and_archived_owner_reads(setup_admin_api):
    d = setup_admin_api
    owner = User(
        id=uuid4(), role="garage_owner", is_active=True, name=f"Zero owner {uuid4()}",
        mobile=str(uuid4().int % 10**10).zfill(10),
    )
    d["session"].add(owner)
    await d["session"].flush()
    result = await d["client"].get(BASE+"/garage-owners", headers=headers(d["admin"]),
                                  params={"search": owner.name})
    item = result.json()["data"]["items"][0]
    assert item["garage_ids"] == [] and item["jobs_created"] == 0
    assert item["completed_job_amount_paise"] == 0
    owner.is_active = False
    owner.deleted_at = datetime.now(timezone.utc)
    await d["session"].flush()
    result = await d["client"].get(BASE+"/garage-owners", headers=headers(d["admin"]),
                                  params={"search": owner.name})
    assert result.json()["data"]["total"] == 0
    retained = await d["client"].get(BASE+"/garage-owners", headers=headers(d["admin"]),
                                    params={"search": owner.name, "status": "DELETED"})
    assert retained.json()["data"]["items"][0]["account_status"] == "DELETED"
    assert (await d["client"].get(BASE+f"/garage-owners/{owner.id}", headers=headers(d["admin"]))).status_code == 404
    assert (await d["client"].get(BASE+f"/garage-owners/{owner.id}?include_deleted=true",
                                 headers=headers(d["admin"]))).status_code == 200


async def test_booking_detail_links_and_missing_history_are_explicit(setup_admin_api):
    d = setup_admin_api
    d["ready"].booking_id = d["booking"].id
    d["booking"].notes = "A generic note, not a recorded decision reason"
    await d["session"].flush()
    result = await d["client"].get(BASE+f"/bookings/{d['booking'].id}", headers=headers(d["admin"]))
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["linked_job_ids"] == [str(d["ready"].id)]
    assert data["decision_actor"] is None and data["decision_reason"] is None
    assert data["decision_timestamp"] is None
    assert len(data["missing_history"]) == 3
    d["booking"].deleted_at = datetime.now(timezone.utc)
    await d["session"].flush()
    for path in [f"/bookings/{d['booking'].id}", f"/activity/service-funnels/{d['booking'].id}"]:
        assert (await d["client"].get(BASE+path, headers=headers(d["admin"]))).status_code == 404


async def test_related_previews_are_bounded_and_complete_lists_remain_pageable(setup_admin_api):
    d = setup_admin_api
    for index in range(101):
        d["session"].add(Garage(
            id=uuid4(), user_id=d["owner"].id, name=f"Bounded garage {index}", owner="Fixture",
        ))
        d["session"].add(Job(
            id=uuid4(), garage_id=d["garage"].id, booking_id=d["booking"].id,
            job_number=f"BOUNDED-JOB-{index}",
        ))
    await d["session"].flush()
    auth = headers(d["admin"])
    owner = await d["client"].get(BASE+f"/garage-owners/{d['owner'].id}", headers=auth)
    assert owner.status_code == 200, owner.text
    data = owner.json()["data"]
    assert data["total_garages"] == 102 and len(data["garage_ids"]) == len(data["garages"]) == 100
    assert data["related_garages_truncated"] is True
    booking = await d["client"].get(BASE+f"/bookings/{d['booking'].id}", headers=auth)
    assert len(booking.json()["data"]["linked_job_ids"]) == 100
    assert booking.json()["data"]["linked_jobs_truncated"] is True
    jobs = await d["client"].get(BASE+"/jobs", headers=auth, params={
        "booking_id":str(d["booking"].id),"page_size":100,
    })
    assert jobs.status_code == 200, jobs.text
    assert jobs.json()["data"]["total"] == 101 and jobs.json()["data"]["pages"] == 2


async def test_timezone_boundaries_and_consistent_dashboard_analytics_lists(setup_admin_api):
    d = setup_admin_api
    instant = datetime(2026,10,10,23,0,tzinfo=timezone.utc)
    d["garage"].city = f"Timezone city {uuid4()}"
    d["booking"].created_at = instant
    d["booking"].status = BookingStatus.REJECTED
    d["ready"].created_at = instant
    d["completed"].created_at = datetime(2026,10,9,23,0,tzinfo=timezone.utc)
    d["completed"].completed_at = instant
    await d["session"].flush()
    params = {"garage_id": str(d["garage"].id), "city": d["garage"].city,
              "date_from": "2026-10-11", "date_to": "2026-10-11", "timezone": "Asia/Kolkata"}
    auth = headers(d["admin"])
    booking_list = await d["client"].get(BASE+"/bookings", params=params, headers=auth)
    assert booking_list.status_code == 200, booking_list.text
    assert booking_list.json()["data"]["total"] == 1
    job_list = await d["client"].get(BASE+"/jobs", params=params, headers=auth)
    assert job_list.json()["data"]["total"] == 1
    dashboard = await d["client"].get(BASE+"/dashboard", params=params, headers=auth)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["data"]["total_jobs"] == 1
    assert dashboard.json()["data"]["total_bookings"] == 1
    assert dashboard.json()["data"]["total_revenue"] == 118
    analytics = await d["client"].get(BASE+"/analytics", params={**params, "period":"daily"}, headers=auth)
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["data"]["total_jobs"] == 1
    assert analytics.json()["data"]["total_revenue"] == 118
    assert analytics.json()["data"]["graph_data"][0]["completed_count"] == 1
    exceptions = await d["client"].get(BASE+"/bookings/exception-statistics", params=params, headers=auth)
    assert exceptions.status_code == 200, exceptions.text
    assert exceptions.json()["data"]["rejected"] == 1
    assert exceptions.json()["data"]["reason_counts"] == {"UNSPECIFIED":1}
    assert exceptions.json()["data"]["reason_history_available"] is False
    utc = await d["client"].get(BASE+"/bookings", params={**params,"timezone":"UTC"}, headers=auth)
    assert utc.json()["data"]["total"] == 0


async def test_timeline_and_activity_pagination_and_recorded_funnel(setup_admin_api):
    d = setup_admin_api
    d["ready"].booking_id = d["completed"].booking_id = d["booking"].id
    for status, day in [("READY",11),("OPEN",10)]:
        d["session"].add(JobTimeline(
            id=uuid4(), job_id=d["ready"].id, status=status,
            created_at=datetime(2026,10,day,12,0,tzinfo=timezone.utc),
        ))
    await d["session"].flush()
    auth = headers(d["admin"])
    timeline = await d["client"].get(BASE+f"/jobs/{d['ready'].id}/timeline?page_size=1", headers=auth)
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["data"]["total"] == 2
    assert timeline.json()["data"]["items"][0]["status"] == "OPEN"
    page_two = await d["client"].get(BASE+f"/jobs/{d['ready'].id}/timeline?page_size=1&page=2", headers=auth)
    assert page_two.json()["data"]["items"][0]["status"] == "READY"
    params = {"garage_id":str(d["garage"].id),"page_size":100}
    activity = await d["client"].get(BASE+"/activity",params=params,headers=auth)
    assert activity.status_code == 200, activity.text
    data = activity.json()["data"]
    assert data["total"] == 6
    assert all(item["garage_id"] == str(d["garage"].id) for item in data["items"])
    assert len({item["id"] for item in data["items"]}) == 6
    assert [item["timestamp"] for item in data["items"]] == sorted(
        [item["timestamp"] for item in data["items"]],reverse=True,
    )
    completed = await d["client"].get(BASE+"/activity",params={**params,"event_type":"JOB_COMPLETED"},headers=auth)
    assert completed.json()["data"]["total"] == 1
    funnel = await d["client"].get(BASE+f"/activity/service-funnels/{d['booking'].id}",headers=auth)
    assert funnel.status_code == 200, funnel.text
    assert set(funnel.json()["data"]["job_ids"]) == {str(d["ready"].id),str(d["completed"].id)}
    assert funnel.json()["data"]["events"]["total"] == 6
    assert funnel.json()["data"]["data_coverage"]["payments"] is False
    d["garage"].deleted_at = datetime.now(timezone.utc)
    await d["session"].flush()
    assert (await d["client"].get(BASE+f"/jobs/{d['ready'].id}/timeline",headers=auth)).status_code == 404
    assert (await d["client"].get(BASE+"/activity",params=params,headers=auth)).json()["data"]["total"] == 0


async def test_audit_detail_and_timezone_filtered_history(setup_admin_api):
    d = setup_admin_api
    action = f"phase_{uuid4()}"
    audit = AdminAuditLog(
        id=uuid4(),actor_id=d["admin"].id,action=action,resource_id=d["garage"].id,
        details={"before":{"is_active":True},"after":{"is_active":False}},
        created_at=datetime(2026,10,10,23,0,tzinfo=timezone.utc),
    )
    d["session"].add(audit)
    await d["session"].flush()
    auth = headers(d["admin"])
    detail = await d["client"].get(BASE+f"/audit-logs/{audit.id}",headers=auth)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["details"] == audit.details
    logs = await d["client"].get(BASE+"/audit-logs",headers=auth,params={
        "actor_id":str(d["admin"].id),"action":action,"date_from":"2026-10-11",
        "date_to":"2026-10-11","timezone":"Asia/Kolkata",
    })
    assert logs.status_code == 200
    assert logs.json()["data"]["total"] == 1


@pytest.mark.parametrize("path,code",[
    ("/jobs?date_from=2026-10-12&date_to=2026-10-11",400),
    ("/bookings?timezone=Not/AZone",422),
    ("/activity?event_type=PAYMENT_CONFIRMED",422),
    ("/garage-owners?status=INVALID",422),
    ("/activity?page_size=101",422),
    ("/dashboard?service_id=unsupported",422),
    ("/garage-owners?min_rating=6",422),
    ("/garages?verification_status=INVALID",422),
    ("/analytics?start_date=2026-10-10&date_from=2026-10-11",422),
    ("/activity?date_from=2020-01-01&date_to=2026-10-12",422),
    ("/jobs?city=%20%20",422),
])
async def test_unavailable_filters_are_not_silently_ignored(setup_admin_api,path,code):
    d = setup_admin_api
    response = await d["client"].get(BASE+path,headers=headers(d["admin"]))
    assert response.status_code == code, response.text
