"""Shared fixtures for integration tests."""
import asyncio
import uuid

import pytest
import pytest_asyncio
import httpx

BASE_URL = "http://localhost:8080"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def auth_token():
    """Sign up a fresh test user and return a valid JWT."""
    mobile = f"8{uuid.uuid4().int % 10**9:09d}"

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Integration Test"})
        assert r.status_code == 201, r.text

    # Read OTP directly from DB
    from app.database.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as session:
        user = (await session.execute(select(User).where(User.mobile == mobile))).scalar_one()
        otp = user.otp

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": otp})
        assert r.status_code == 200, r.text
        return r.json()["data"]["access_token"]


@pytest_asyncio.fixture(scope="session")
async def garage_id(auth_token):
    """Create a garage and return its ID."""
    import uuid as uuidlib
    from app.database.session import async_session
    from app.models.garage import Garage
    from app.models.user import User
    from sqlalchemy import select

    # Get user id from token
    from app.core.security import decode_access_token
    user_id = decode_access_token(auth_token)

    async with async_session() as session:
        user = await session.get(User, uuidlib.UUID(user_id))
        existing = (
            await session.execute(
                select(Garage).where(Garage.user_id == user.id, Garage.deleted_at.is_(None))
            )
        ).scalar_one_or_none()

        if not existing:
            g = Garage(
                id=uuidlib.uuid4(),
                user_id=user.id,
                name="Test Garage",
                owner="Test Owner",
            )
            session.add(g)
            await session.commit()
            return str(g.id)
        return str(existing.id)


@pytest.fixture
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
