from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

log = logging.getLogger("legal_workflow")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request ID, security headers, structured access logging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000.0
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        log.info(
            "request_id=%s method=%s path=%s status=%s ms=%.1f",
            rid,
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limit per client IP (in-memory). Set to 0 to disable."""

    _hits: defaultdict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        limit = settings.rate_limit_requests_per_minute
        if limit <= 0:
            return await call_next(request)
        path = request.url.path
        if path in ("/health", "/ready", "/", "/favicon.ico"):
            return await call_next(request)
        if path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/redoc"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = 60.0
        lst = RateLimitMiddleware._hits[ip]
        lst[:] = [t for t in lst if now - t < window]
        if len(lst) >= limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded; retry after one minute."},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        lst.append(now)
        return await call_next(request)
