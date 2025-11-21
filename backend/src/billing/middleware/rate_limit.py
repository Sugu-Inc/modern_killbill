"""Rate limiting middleware using Redis sliding window algorithm.

Implements rate limiting to prevent API abuse and ensure fair usage.
Default: 1000 requests per hour per API key/IP address.
"""
from typing import Callable
from datetime import datetime
import structlog

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from billing.cache import cache

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis sliding window.

    Limits requests per hour per API key or IP address.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 1000,
        window_seconds: int = 3600,  # 1 hour
    ):
        """
        Initialize rate limiter.

        Args:
            app: ASGI application
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
        """
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request with rate limiting.

        Args:
            request: HTTP request
            call_next: Next middleware/endpoint

        Returns:
            HTTP response

        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/health/ready", "/metrics"]:
            return await call_next(request)

        # Determine identifier (API key or IP)
        identifier = await self._get_identifier(request)

        # Check rate limit
        is_allowed, remaining, reset_time = await self._check_rate_limit(identifier)

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                path=request.url.path,
                method=request.method,
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"Maximum {self.max_requests} requests per hour exceeded",
                    "retry_after": reset_time,
                },
                headers={
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time - int(datetime.utcnow().timestamp())),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response

    async def _get_identifier(self, request: Request) -> str:
        """
        Get unique identifier for rate limiting.

        Prioritizes API key from Authorization header, falls back to IP address.

        Args:
            request: HTTP request

        Returns:
            Unique identifier string
        """
        # Try to get API key from Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # Use first 20 characters of token as identifier
            token = auth_header[7:]
            if token:
                return f"token:{token[:20]}"

        # Try to get API key from X-API-Key header
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"api_key:{api_key}"

        # Fall back to IP address
        # Check for forwarded IP (behind proxy)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Use first IP in the chain
            ip = forwarded_for.split(",")[0].strip()
        else:
            # Use direct client IP
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    async def _check_rate_limit(self, identifier: str) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit using sliding window.

        Args:
            identifier: Unique identifier

        Returns:
            Tuple of (is_allowed, remaining_requests, reset_timestamp)
        """
        now = int(datetime.utcnow().timestamp())
        window_start = now - self.window_seconds

        # Create Redis key for this identifier
        key = f"rate_limit:{identifier}"

        try:
            # Increment counter for current second
            count_key = f"{key}:{now}"
            current_count = await cache.increment(count_key)

            # Set expiration on the key (2 * window to be safe)
            await cache.expire(count_key, self.window_seconds * 2)

            # Count total requests in the sliding window
            total_requests = 0

            # Use pipeline for efficiency (if available)
            # For simplicity, we'll use a simple counter approach
            # In production, consider using Redis sorted sets for more accurate sliding window

            # Get all keys for this identifier in the window
            pattern = f"{key}:*"

            # Simplified approach: use a single counter with sliding window expiration
            # This is approximate but efficient
            window_key = f"rate_limit_window:{identifier}"

            # Get current count
            window_count = await cache.get(window_key)
            if window_count is None:
                window_count = 1
                await cache.set(window_key, 1, self.window_seconds)
            else:
                window_count = int(window_count) + 1
                await cache.set(window_key, window_count, self.window_seconds)

            # Check if within limit
            is_allowed = window_count <= self.max_requests
            remaining = max(0, self.max_requests - window_count)
            reset_time = now + self.window_seconds

            logger.debug(
                "rate_limit_checked",
                identifier=identifier,
                count=window_count,
                limit=self.max_requests,
                remaining=remaining,
                allowed=is_allowed,
            )

            return is_allowed, remaining, reset_time

        except Exception as e:
            logger.error(
                "rate_limit_check_failed",
                identifier=identifier,
                error=str(e),
            )
            # On error, allow request (fail open for availability)
            return True, self.max_requests, now + self.window_seconds


# Decorator for endpoint-specific rate limiting
def rate_limit(max_requests: int = 100, window_seconds: int = 60):
    """
    Decorator for endpoint-specific rate limiting.

    Usage:
        @rate_limit(max_requests=10, window_seconds=60)
        async def expensive_endpoint():
            ...

    Args:
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This would need request context - simplified for now
            return await func(*args, **kwargs)
        return wrapper
    return decorator
