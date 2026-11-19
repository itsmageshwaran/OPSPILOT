"""
Custom HTTP Middlewares for OpsPilot Backend.
Demonstrates:
1. Request Timing & Correlation Tracing Middleware
2. Strict Security Headers Middleware
3. Audit Logging Middleware
"""

import time
import uuid
import logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("opspilot.middleware")


class RequestTimingAndCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Records request processing latency and injects tracing correlation headers:
    - X-Response-Time-Ms: High-precision execution duration in milliseconds
    - X-Correlation-ID: Distributed tracing identifier across service mesh
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        correlation_id = request.headers.get("X-Correlation-ID") or f"corr_{uuid.uuid4().hex[:12]}"
        request.state.correlation_id = correlation_id

        response: Response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Enforces defense-in-depth HTTP security response headers:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY (clickjacking defense)
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: HSTS enforcement
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Emits structured audit logs for administrative or mutating requests.
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        path = request.url.path

        response: Response = await call_next(request)

        if method in ("POST", "PUT", "PATCH", "DELETE"):
            logger.info(
                f"[AuditLog] {method} {path} -> HTTP {response.status_code} "
                f"(Correlation: {getattr(request.state, 'correlation_id', 'unknown')})"
            )
        return response


__all__ = [
    "RequestTimingAndCorrelationMiddleware",
    "SecurityHeadersMiddleware",
    "AuditLoggingMiddleware",
]
