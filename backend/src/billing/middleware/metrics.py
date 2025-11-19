"""Prometheus metrics middleware for API monitoring."""
import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Define Prometheus metrics
api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    labelnames=["method", "path", "status_code"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

api_requests_total = Counter(
    "api_requests_total",
    "Total API requests",
    labelnames=["method", "path", "status_code"],
)

api_errors_total = Counter(
    "api_errors_total",
    "Total API errors",
    labelnames=["method", "path", "error_type"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware for collecting Prometheus metrics on API requests.

    Tracks:
    - Request duration histogram (api_request_duration_seconds)
    - Request counter (api_requests_total)
    - Error counter (api_errors_total)
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        Process request and collect metrics.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Response: HTTP response from route handler
        """
        # Skip metrics collection for /metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        # Start timer
        start_time = time.time()

        # Extract path template for consistent labeling
        path = request.url.path

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Record metrics
            api_request_duration_seconds.labels(
                method=request.method,
                path=path,
                status_code=response.status_code,
            ).observe(duration)

            api_requests_total.labels(
                method=request.method,
                path=path,
                status_code=response.status_code,
            ).inc()

            return response

        except Exception as exc:
            # Record error metric
            api_errors_total.labels(
                method=request.method,
                path=path,
                error_type=type(exc).__name__,
            ).inc()

            raise
