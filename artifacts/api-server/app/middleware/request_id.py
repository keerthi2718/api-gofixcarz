import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from loguru import logger


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request and log it."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        with logger.contextualize(request_id=request_id):
            logger.info(f"{request.method} {request.url.path}")
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(f"{request.method} {request.url.path} → {response.status_code}")
        return response
