"""Integration tests for the Jobs, Customers, and Vehicles endpoints."""
import uuid

import pytest
import httpx

BASE_URL = "http://localhost:8080"


@pytest.mark.asyncio
async def test_customer_crud(auth_token, garage_id, headers):
    mobile = f"5{uuid.uuid4().int % 10**9:09d}"

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Create
        r = await client.post(
            "/api/v1/customers",
            headers=headers,
            json={"name": "Test Customer", "mobile": mobile},
        )
        assert r.status_code == 201
        cid = r.json()["data"]["id"]

        # List
        r = await client.get("/api/v1/customers", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 1

        # Get by id
        r = await client.get(f"/api/v1/customers/{cid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "Test Customer"

        # Update
        r = await client.put(f"/api/v1/customers/{cid}", headers=headers, json={"notes": "VIP"})
        assert r.status_code == 200
        assert r.json()["data"]["notes"] == "VIP"

        # Delete
        r = await client.delete(f"/api/v1/customers/{cid}", headers=headers)
        assert r.status_code == 200

        # Confirm gone
        r = await client.get(f"/api/v1/customers/{cid}", headers=headers)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_full_job_lifecycle(auth_token, garage_id, headers):
    mobile = f"4{uuid.uuid4().int % 10**9:09d}"

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Create customer
        r = await client.post(
            "/api/v1/customers",
            headers=headers,
            json={"name": "Job Test Customer", "mobile": mobile},
        )
        cid = r.json()["data"]["id"]

        # Create vehicle
        plate = f"TT{uuid.uuid4().int % 10000:04d}AA"
        r = await client.post(
            "/api/v1/vehicles",
            headers=headers,
            json={
                "customer_id": cid,
                "make": "Honda",
                "model": "Civic",
                "year": 2021,
                "registration_plate": plate,
            },
        )
        assert r.status_code == 201
        vid = r.json()["data"]["id"]

        # Create job
        r = await client.post(
            "/api/v1/jobs",
            headers=headers,
            json={"customer_id": cid, "vehicle_id": vid, "description": "Test job", "estimated_amount": 1000},
        )
        assert r.status_code == 201
        jid = r.json()["data"]["id"]
        assert r.json()["data"]["status"] == "OPEN"

        # Advance to IN_PROGRESS
        r = await client.patch(
            f"/api/v1/jobs/{jid}/status",
            headers=headers,
            json={"status": "IN_PROGRESS", "notes": "Started"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "IN_PROGRESS"

        # Invalid transition
        r = await client.patch(
            f"/api/v1/jobs/{jid}/status",
            headers=headers,
            json={"status": "OPEN"},
        )
        assert r.status_code == 400

        # Complete
        r = await client.patch(
            f"/api/v1/jobs/{jid}/complete",
            headers=headers,
            json={"final_amount": 950, "notes": "Done"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "COMPLETED"

        # Detail shows timeline
        r = await client.get(f"/api/v1/jobs/{jid}", headers=headers)
        assert r.status_code == 200
        assert len(r.json()["data"]["timelines"]) >= 3

        # Dashboard reflects the job
        r = await client.get("/api/v1/dashboard", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["completed_jobs"] >= 1

        # Analytics
        r = await client.get("/api/v1/analytics?period=monthly", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["total_jobs"] >= 1
