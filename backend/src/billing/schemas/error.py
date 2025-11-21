"""Structured error response schemas."""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    field: str | None = Field(default=None, description="Field that caused the error (for validation errors)")
    value: Any | None = Field(default=None, description="Invalid value (for validation errors)")


class ErrorResponse(BaseModel):
    """Standard error response structure.

    This provides consistent error responses across the API with:
    - HTTP status code
    - Machine-readable error codes
    - Human-readable messages
    - Remediation hints
    - Request tracing information
    """

    error: str = Field(..., description="Error type (e.g., 'ValidationError', 'NotFound', 'Forbidden')")
    message: str = Field(..., description="Primary error message")
    details: list[ErrorDetail] | None = Field(
        default=None, description="Detailed error information (for validation errors)"
    )
    remediation: str | None = Field(default=None, description="Suggestion for fixing the error")
    request_id: str | None = Field(default=None, description="Request ID for tracing")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    documentation_url: str | None = Field(default=None, description="Link to relevant documentation")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid input data",
                "details": [
                    {
                        "code": "invalid_email",
                        "message": "Email address is not valid",
                        "field": "email",
                        "value": "not-an-email",
                    }
                ],
                "remediation": "Provide a valid email address in the format: user@example.com",
                "request_id": "req_1234567890",
                "timestamp": "2024-01-15T10:30:00Z",
                "documentation_url": "https://docs.example.com/api/errors#validation",
            }
        }


class ValidationErrorResponse(ErrorResponse):
    """Validation error response with field-level details."""

    error: str = Field(default="ValidationError", description="Error type")


class NotFoundErrorResponse(ErrorResponse):
    """Not found error response."""

    error: str = Field(default="NotFound", description="Error type")


class ForbiddenErrorResponse(ErrorResponse):
    """Forbidden error response for authorization failures."""

    error: str = Field(default="Forbidden", description="Error type")


class RateLimitErrorResponse(ErrorResponse):
    """Rate limit exceeded error response."""

    error: str = Field(default="RateLimitExceeded", description="Error type")
    retry_after: int | None = Field(default=None, description="Seconds until rate limit resets")


class InternalServerErrorResponse(ErrorResponse):
    """Internal server error response."""

    error: str = Field(default="InternalServerError", description="Error type")


# Error codes enum for consistency
class ErrorCode:
    """Standard error codes used across the API."""

    # Validation errors (400)
    INVALID_EMAIL = "invalid_email"
    INVALID_CURRENCY = "invalid_currency"
    INVALID_AMOUNT = "invalid_amount"
    INVALID_DATE = "invalid_date"
    INVALID_UUID = "invalid_uuid"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_ENUM_VALUE = "invalid_enum_value"
    VALUE_TOO_SMALL = "value_too_small"
    VALUE_TOO_LARGE = "value_too_large"

    # Business logic errors (400)
    INSUFFICIENT_FUNDS = "insufficient_funds"
    DUPLICATE_RESOURCE = "duplicate_resource"
    INVALID_STATE_TRANSITION = "invalid_state_transition"
    SUBSCRIPTION_ALREADY_ACTIVE = "subscription_already_active"
    INVOICE_ALREADY_PAID = "invoice_already_paid"
    INVOICE_ALREADY_VOID = "invoice_already_void"
    CANNOT_DELETE_DEFAULT_PAYMENT_METHOD = "cannot_delete_default_payment_method"

    # Not found errors (404)
    ACCOUNT_NOT_FOUND = "account_not_found"
    PLAN_NOT_FOUND = "plan_not_found"
    SUBSCRIPTION_NOT_FOUND = "subscription_not_found"
    INVOICE_NOT_FOUND = "invoice_not_found"
    PAYMENT_NOT_FOUND = "payment_not_found"
    PAYMENT_METHOD_NOT_FOUND = "payment_method_not_found"

    # Authorization errors (403)
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    ACCOUNT_BLOCKED = "account_blocked"

    # Rate limiting (429)
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # External service errors (502, 503)
    STRIPE_API_ERROR = "stripe_api_error"
    DATABASE_ERROR = "database_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"

    # Internal errors (500)
    INTERNAL_ERROR = "internal_error"
    UNHANDLED_EXCEPTION = "unhandled_exception"


# Remediation hints for common errors
REMEDIATION_HINTS = {
    ErrorCode.INVALID_EMAIL: "Provide a valid email address in the format: user@example.com",
    ErrorCode.INVALID_CURRENCY: "Use a valid 3-letter ISO 4217 currency code (e.g., USD, EUR, GBP)",
    ErrorCode.INVALID_AMOUNT: "Provide a positive amount in cents (e.g., 1000 for $10.00)",
    ErrorCode.INVALID_UUID: "Provide a valid UUID v4 identifier",
    ErrorCode.ACCOUNT_NOT_FOUND: "Verify the account ID is correct and the account exists",
    ErrorCode.INVOICE_ALREADY_PAID: "Cannot modify a paid invoice. Issue a credit or refund instead.",
    ErrorCode.INVOICE_ALREADY_VOID: "Cannot modify a voided invoice. Create a new invoice instead.",
    ErrorCode.STRIPE_API_ERROR: "Stripe payment processing is temporarily unavailable. Please try again later.",
    ErrorCode.RATE_LIMIT_EXCEEDED: "Too many requests. Please slow down and try again after the retry period.",
    ErrorCode.DATABASE_ERROR: "Database temporarily unavailable. Please try again in a few moments.",
}
