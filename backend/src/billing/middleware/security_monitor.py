"""
Security event monitoring middleware for SOC2 compliance.

Tracks security-relevant events and alerts on suspicious patterns:
- Failed authentication attempts
- Unusual access patterns (rapid requests, unusual endpoints)
- Privilege escalation attempts
- Suspicious IP addresses

Implements SOC2 CC7.2 monitoring requirements.
"""

from datetime import datetime, timedelta
from typing import Optional
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import status

from billing.cache import cache

logger = structlog.get_logger(__name__)


class SecurityEventMonitor(BaseHTTPMiddleware):
    """
    Middleware for monitoring and alerting on security events.

    Tracks:
    - Failed authentication attempts (401, 403 responses)
    - Rate limit violations
    - Unusual access patterns
    - Suspicious user behavior

    Alerts when thresholds are breached to enable rapid incident response.
    """

    def __init__(
        self,
        app,
        failed_auth_threshold: int = 5,  # Alert after 5 failed attempts in window
        window_minutes: int = 15,  # Time window for counting events
        rate_threshold: int = 100,  # Alert after 100 requests in window
        enable_ip_tracking: bool = True,  # Track by IP address
    ):
        """
        Initialize security event monitor.

        Args:
            app: FastAPI application
            failed_auth_threshold: Number of failed auth attempts before alert
            window_minutes: Time window for event counting (minutes)
            rate_threshold: Number of requests before rate alert
            enable_ip_tracking: Whether to track events by IP address
        """
        super().__init__(app)
        self.failed_auth_threshold = failed_auth_threshold
        self.window_minutes = window_minutes
        self.rate_threshold = rate_threshold
        self.enable_ip_tracking = enable_ip_tracking

        # Cache key prefixes
        self.FAILED_AUTH_PREFIX = "security:failed_auth"
        self.RATE_LIMIT_PREFIX = "security:rate_limit"
        self.ALERT_SENT_PREFIX = "security:alert_sent"

        logger.info(
            "security_monitor_initialized",
            failed_auth_threshold=self.failed_auth_threshold,
            window_minutes=self.window_minutes,
            rate_threshold=self.rate_threshold,
        )

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Handles X-Forwarded-For header for proxied requests.

        Args:
            request: HTTP request

        Returns:
            Client IP address
        """
        # Check X-Forwarded-For header (set by load balancers/proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first (client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header (alternative proxy header)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct connection IP
        if request.client:
            return request.client.host

        return "unknown"

    def _get_user_id(self, request: Request) -> Optional[str]:
        """
        Extract user ID from request if authenticated.

        Args:
            request: HTTP request

        Returns:
            User ID or None if not authenticated
        """
        # User ID would be set by auth middleware in request.state
        return getattr(request.state, "user_id", None)

    async def _track_failed_auth(self, request: Request, ip_address: str):
        """
        Track failed authentication attempt.

        Args:
            request: HTTP request
            ip_address: Client IP address
        """
        cache_key = f"{self.FAILED_AUTH_PREFIX}:{ip_address}"
        ttl_seconds = self.window_minutes * 60

        # Increment counter
        try:
            current_count = await cache.get(cache_key) or 0
            current_count = int(current_count)
            new_count = current_count + 1

            await cache.set(cache_key, str(new_count), ttl=ttl_seconds)

            logger.warning(
                "failed_auth_attempt",
                ip_address=ip_address,
                path=request.url.path,
                method=request.method,
                user_agent=request.headers.get("User-Agent"),
                attempt_count=new_count,
            )

            # Check if threshold breached
            if new_count >= self.failed_auth_threshold:
                await self._alert_failed_auth_threshold(ip_address, new_count)

        except Exception as e:
            logger.exception("failed_to_track_auth_failure", error=str(e))

    async def _track_rate_limit(self, request: Request, ip_address: str):
        """
        Track request rate per IP.

        Args:
            request: HTTP request
            ip_address: Client IP address
        """
        cache_key = f"{self.RATE_LIMIT_PREFIX}:{ip_address}"
        ttl_seconds = self.window_minutes * 60

        try:
            current_count = await cache.get(cache_key) or 0
            current_count = int(current_count)
            new_count = current_count + 1

            await cache.set(cache_key, str(new_count), ttl=ttl_seconds)

            # Check if threshold breached
            if new_count >= self.rate_threshold:
                # Only alert once per window
                alert_key = f"{self.ALERT_SENT_PREFIX}:rate:{ip_address}"
                alert_sent = await cache.get(alert_key)

                if not alert_sent:
                    await self._alert_rate_threshold(ip_address, new_count)
                    await cache.set(alert_key, "1", ttl=ttl_seconds)

        except Exception as e:
            logger.exception("failed_to_track_rate", error=str(e))

    async def _alert_failed_auth_threshold(self, ip_address: str, count: int):
        """
        Send alert when failed auth threshold is breached.

        Args:
            ip_address: Client IP address
            count: Number of failed attempts
        """
        # Check if alert already sent for this IP in current window
        alert_key = f"{self.ALERT_SENT_PREFIX}:auth:{ip_address}"
        alert_sent = await cache.get(alert_key)

        if alert_sent:
            return  # Already alerted for this window

        # Mark alert as sent
        await cache.set(
            alert_key,
            "1",
            ttl=self.window_minutes * 60
        )

        # Log security alert (would integrate with PagerDuty, Slack, etc.)
        logger.error(
            "security_alert_failed_auth_threshold",
            severity="HIGH",
            ip_address=ip_address,
            failed_attempts=count,
            threshold=self.failed_auth_threshold,
            window_minutes=self.window_minutes,
            action_required="Review failed authentication attempts and consider IP blocking",
            timestamp=datetime.utcnow().isoformat(),
        )

        # TODO: Integrate with alerting system (PagerDuty, Slack, email)
        # TODO: Consider automatic IP blocking after threshold

    async def _alert_rate_threshold(self, ip_address: str, count: int):
        """
        Send alert when rate limit threshold is breached.

        Args:
            ip_address: Client IP address
            count: Number of requests
        """
        logger.warning(
            "security_alert_rate_threshold",
            severity="MEDIUM",
            ip_address=ip_address,
            request_count=count,
            threshold=self.rate_threshold,
            window_minutes=self.window_minutes,
            action_required="Review unusual request patterns",
            timestamp=datetime.utcnow().isoformat(),
        )

        # TODO: Integrate with alerting system

    def _is_auth_endpoint(self, path: str) -> bool:
        """
        Check if path is an authentication endpoint.

        Args:
            path: Request path

        Returns:
            True if auth endpoint
        """
        auth_endpoints = [
            "/v1/auth/login",
            "/v1/auth/refresh",
            "/v1/auth/token",
        ]
        return any(path.startswith(endpoint) for endpoint in auth_endpoints)

    def _is_sensitive_endpoint(self, path: str) -> bool:
        """
        Check if path is a sensitive endpoint requiring extra monitoring.

        Args:
            path: Request path

        Returns:
            True if sensitive endpoint
        """
        sensitive_patterns = [
            "/v1/payments",
            "/v1/credits",
            "/v1/accounts",
            "/admin",
        ]
        return any(pattern in path for pattern in sensitive_patterns)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Monitor request and response for security events.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            Response with security monitoring applied
        """
        ip_address = self._get_client_ip(request)
        path = request.url.path
        method = request.method

        # Track request rate
        if self.enable_ip_tracking:
            await self._track_rate_limit(request, ip_address)

        # Process request
        response = await call_next(request)

        # Monitor response for security events
        status_code = response.status_code

        # Track failed authentication (401, 403)
        if status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]:
            await self._track_failed_auth(request, ip_address)

            # Extra logging for sensitive endpoints
            if self._is_sensitive_endpoint(path):
                logger.warning(
                    "sensitive_endpoint_access_denied",
                    ip_address=ip_address,
                    path=path,
                    method=method,
                    status_code=status_code,
                    user_id=self._get_user_id(request),
                )

        # Monitor successful access to sensitive endpoints
        elif status_code == status.HTTP_200_OK and self._is_sensitive_endpoint(path):
            logger.info(
                "sensitive_endpoint_access",
                ip_address=ip_address,
                path=path,
                method=method,
                user_id=self._get_user_id(request),
            )

        # Monitor privilege escalation attempts (accessing admin endpoints)
        if "/admin" in path and status_code == status.HTTP_403_FORBIDDEN:
            logger.error(
                "privilege_escalation_attempt",
                severity="HIGH",
                ip_address=ip_address,
                path=path,
                method=method,
                user_id=self._get_user_id(request),
                user_agent=request.headers.get("User-Agent"),
            )

        return response


async def get_security_stats(ip_address: Optional[str] = None) -> dict:
    """
    Get security event statistics for monitoring dashboard.

    Args:
        ip_address: Optional IP to get stats for specific address

    Returns:
        Dictionary of security statistics
    """
    # This would be called by an admin endpoint to view security stats

    if ip_address:
        failed_auth_key = f"security:failed_auth:{ip_address}"
        rate_key = f"security:rate_limit:{ip_address}"

        failed_attempts = await cache.get(failed_auth_key) or 0
        request_count = await cache.get(rate_key) or 0

        return {
            "ip_address": ip_address,
            "failed_auth_attempts": int(failed_attempts),
            "request_count": int(request_count),
            "monitored": True,
        }

    # Return aggregated stats
    # In production, this would query all keys matching pattern
    return {
        "monitoring_enabled": True,
        "failed_auth_threshold": 5,
        "rate_threshold": 100,
        "window_minutes": 15,
    }
