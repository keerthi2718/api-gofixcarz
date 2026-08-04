import json
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.log import logger, setup_logging
from app.database.session import async_session, engine

setup_logging()

START_TIME = time.time()

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ── Body-cache middleware ─────────────────────────────────────────────────────
class OTPBodyCacheMiddleware(BaseHTTPMiddleware):
    """Pre-read JSON body for OTP routes so the sync rate-limit key_func can access it.

    Starlette caches the raw body internally after the first read, so FastAPI's
    dependency injection can still parse it normally afterwards.
    """
    _OTP_PATHS = frozenset({"/api/v1/auth/sign-in", "/api/v1/auth/send-otp"})

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._OTP_PATHS:
            try:
                raw = await request.body()
                request.state._body_json = json.loads(raw)
            except Exception:
                request.state._body_json = {}
        return await call_next(request)


async def _delete_expired_refresh_tokens() -> None:
    """Scheduled job: purge expired refresh tokens from the database."""
    try:
        async with async_session() as session:
            from app.repositories.refresh_token_repository import RefreshTokenRepository  # noqa: PLC0415
            repo = RefreshTokenRepository(session)
            deleted = await repo.delete_expired()
            await session.commit()
        logger.info(f"Expired refresh token cleanup: {deleted} row(s) deleted")
    except Exception:
        logger.exception("Expired refresh token cleanup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    scheduler = AsyncIOScheduler()
    # Run once at startup, then every 24 hours
    scheduler.add_job(
        _delete_expired_refresh_tokens,
        trigger="interval",
        hours=24,
        id="delete_expired_refresh_tokens",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    # Kick off an immediate first run so stale rows are cleared on restart too
    await _delete_expired_refresh_tokens()

    yield

    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Attach limiter to app state so SlowAPIMiddleware can find it
app.state.limiter = limiter

# ── Middleware (last-added = outermost = runs first) ──────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global per-IP rate limit (200 req/min)
app.add_middleware(SlowAPIMiddleware)

# OTP body cache must wrap SlowAPIMiddleware so the mobile key is ready before
# slowapi evaluates the per-endpoint rate-limit key function.
app.add_middleware(OTPBodyCacheMiddleware)

from app.middleware.request_id import RequestIDMiddleware  # noqa: E402

app.add_middleware(RequestIDMiddleware)


# ── Exception handlers ────────────────────────────────────────────────────────
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "data": None,
            "errors": exc.errors,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(l) for l in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Validation error",
            "data": None,
            "errors": errors,
            "status_code": 422,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "data": None,
            "errors": [],
            "status_code": 500,
        },
    )


# ── Health & version ─────────────────────────────────────────────────────────
health_router = APIRouter(tags=["Health"])


@health_router.get("/api/health")
@health_router.get("/api/healthz")
async def health():
    db_ok = False
    pool_stats: dict = {}
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
        pool = engine.sync_engine.pool
        pool_stats = {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
    return {
        "success": True,
        "message": "OK",
        "data": {
            "status": "healthy" if db_ok else "degraded",
            "database": "connected" if db_ok else "disconnected",
            "uptime_seconds": round(time.time() - START_TIME, 2),
            "version": settings.APP_VERSION,
            "pool": pool_stats,
        },
        "errors": [],
        "status_code": 200,
    }


@health_router.get("/api/version")
async def version():
    return {
        "success": True,
        "message": "Version info",
        "data": {
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        },
        "errors": [],
        "status_code": 200,
    }


app.include_router(health_router)

# ── API v1 ───────────────────────────────────────────────────────────────────
from app.api.v1.auth import router as auth_router  # noqa: E402
from app.api.v1.customers import router as customers_router  # noqa: E402
from app.api.v1.vehicles import router as vehicles_router  # noqa: E402
from app.api.v1.jobs import router as jobs_router  # noqa: E402
from app.api.v1.bookings import router as bookings_router  # noqa: E402
from app.api.v1.dashboard import router as dashboard_router  # noqa: E402
from app.api.v1.analytics import router as analytics_router  # noqa: E402
from app.api.v1.profile import router as profile_router  # noqa: E402
from app.api.v1.garage import router as garage_router  # noqa: E402
from app.api.v1.service_packages import router as service_packages_router  # noqa: E402
from app.api.v1.notifications import router as notifications_router  # noqa: E402
from app.api.v1.static import router as static_router  # noqa: E402
from app.api.v1.images import router as images_router  # noqa: E402

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
v1_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
v1_router.include_router(customers_router, prefix="/customers", tags=["Customers"])
v1_router.include_router(vehicles_router, prefix="/vehicles", tags=["Vehicles"])
v1_router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
v1_router.include_router(bookings_router, prefix="/bookings", tags=["Bookings"])
v1_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
v1_router.include_router(profile_router, prefix="/profile", tags=["Profile"])
v1_router.include_router(garage_router, prefix="/garage", tags=["Garage"])
v1_router.include_router(service_packages_router, prefix="/service-packages", tags=["Service Packages"])
v1_router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
v1_router.include_router(static_router, prefix="/static", tags=["Static"])
v1_router.include_router(images_router, prefix="/images", tags=["Images"])

app.include_router(v1_router)
