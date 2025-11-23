"""
Security headers middleware for OWASP best practices.

Implements defense-in-depth security headers to protect against:
- XSS attacks (Content-Security-Policy, X-Content-Type-Options)
- Clickjacking (X-Frame-Options)
- HTTPS enforcement (Strict-Transport-Security)
- Information leakage (Referrer-Policy)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds OWASP-recommended security headers to all responses.

    Headers added:
    - Content-Security-Policy: Restricts resource loading to prevent XSS
    - Strict-Transport-Security: Enforces HTTPS for 1 year
    - X-Frame-Options: Prevents clickjacking by disabling iframes
    - X-Content-Type-Options: Prevents MIME type sniffing
    - Referrer-Policy: Controls referrer information leakage
    - Permissions-Policy: Disables unnecessary browser features
    """

    def __init__(self, app, csp_policy: str | None = None):
        """
        Initialize security headers middleware.

        Args:
            app: FastAPI application
            csp_policy: Optional custom Content-Security-Policy.
                       Defaults to strict policy suitable for API.
        """
        super().__init__(app)

        # Default CSP for API server (no inline scripts, external resources)
        # For web apps serving HTML, this should be customized
        self.csp_policy = csp_policy or (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "  # Allow inline CSS for FastAPI docs
            "img-src 'self' data: https:; "  # Allow images from HTTPS and data URIs
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "  # Prevent embedding in iframes
            "base-uri 'self'; "
            "form-action 'self'"
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Add security headers to response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            Response with security headers added
        """
        response = await call_next(request)

        # Content Security Policy - Prevents XSS by restricting resource sources
        response.headers["Content-Security-Policy"] = self.csp_policy

        # Strict Transport Security - Forces HTTPS for 1 year (31536000 seconds)
        # includeSubDomains applies to all subdomains
        # preload allows inclusion in browser HSTS preload lists
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # X-Frame-Options - Prevents clickjacking by blocking iframe embedding
        response.headers["X-Frame-Options"] = "DENY"

        # X-Content-Type-Options - Prevents MIME type sniffing
        # Forces browsers to respect declared Content-Type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer-Policy - Controls referrer information sent with requests
        # strict-origin-when-cross-origin: Send full URL for same-origin,
        # only origin for cross-origin HTTPS, nothing for HTTPS→HTTP
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy - Disables unnecessary browser features
        # Prevents abuse of geolocation, camera, microphone, etc.
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "camera=(), "
            "microphone=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        # X-XSS-Protection - Legacy header for older browsers
        # Modern browsers use CSP instead, but doesn't hurt to include
        # 1; mode=block enables XSS filter and blocks page if attack detected
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response
