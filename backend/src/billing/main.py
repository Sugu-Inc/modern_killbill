"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from sqlalchemy.exc import SQLAlchemyError
from stripe.error import StripeError

from billing.config import settings
from billing.middleware.logging import setup_logging
from billing.middleware.metrics import MetricsMiddleware

# Setup structured logging
setup_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("application_starting", env=settings.app_env)
    yield
    # Shutdown
    logger.info("application_shutting_down")


# Create FastAPI application
app = FastAPI(
    title="Modern Subscription Billing Platform",
    description="Cloud-native billing platform with REST and GraphQL APIs",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics middleware
app.add_middleware(MetricsMiddleware)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Exception handlers with structured error responses
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle Pydantic validation errors with structured response.

    Returns 422 with detailed field-level validation errors.
    """
    from billing.schemas.error import ErrorDetail, ErrorCode, REMEDIATION_HINTS
    from datetime import datetime
    import uuid

    # Extract request ID from headers or generate one
    request_id = request.headers.get("x-request-id", f"req_{uuid.uuid4().hex[:12]}")

    # Convert Pydantic errors to structured format
    details = []
    for error in exc.errors():
        field_path = ".".join(str(loc) for loc in error["loc"])
        error_type = error["type"]

        # Map Pydantic error types to our error codes
        code_mapping = {
            "value_error.email": ErrorCode.INVALID_EMAIL,
            "value_error.uuid": ErrorCode.INVALID_UUID,
            "type_error.enum": ErrorCode.INVALID_ENUM_VALUE,
            "value_error.missing": ErrorCode.MISSING_REQUIRED_FIELD,
            "type_error.integer": ErrorCode.INVALID_AMOUNT,
        }

        code = code_mapping.get(error_type, "validation_error")

        details.append(
            ErrorDetail(
                code=code,
                message=error["msg"],
                field=field_path,
                value=error.get("input"),
            ).model_dump()
        )

    logger.warning(
        "validation_error",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        error_count=len(details),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "details": details,
            "remediation": "Check the API documentation for correct request format at /docs",
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "documentation_url": f"{request.base_url}docs",
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """
    Handle database errors.

    Returns 503 Service Unavailable for database connection issues.
    """
    from billing.schemas.error import ErrorCode, REMEDIATION_HINTS
    from datetime import datetime
    import uuid

    request_id = request.headers.get("x-request-id", f"req_{uuid.uuid4().hex[:12]}")

    logger.error(
        "database_error",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )

    # Don't expose internal database details in production
    error_message = "Database temporarily unavailable" if settings.app_env == "production" else str(exc)

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "DatabaseError",
            "message": "A database error occurred",
            "details": [
                {
                    "code": ErrorCode.DATABASE_ERROR,
                    "message": error_message,
                }
            ],
            "remediation": REMEDIATION_HINTS.get(ErrorCode.DATABASE_ERROR),
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
        headers={"Retry-After": "30"},  # Suggest retry after 30 seconds
    )


@app.exception_handler(StripeError)
async def stripe_exception_handler(request: Request, exc: StripeError) -> JSONResponse:
    """
    Handle Stripe API errors.

    Returns 502 Bad Gateway for payment gateway errors.
    """
    from billing.schemas.error import ErrorCode, REMEDIATION_HINTS
    from datetime import datetime
    import uuid

    request_id = request.headers.get("x-request-id", f"req_{uuid.uuid4().hex[:12]}")

    stripe_code = getattr(exc, "code", None)
    stripe_message = str(exc)

    logger.error(
        "stripe_error",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        stripe_code=stripe_code,
        stripe_message=stripe_message,
    )

    # Map Stripe error codes to user-friendly messages
    user_message = {
        "card_declined": "Payment method declined. Please try a different payment method.",
        "expired_card": "Payment method has expired. Please use a different payment method.",
        "incorrect_cvc": "Card security code is incorrect. Please check and try again.",
        "processing_error": "Payment processing error. Please try again.",
        "rate_limit": "Too many payment attempts. Please try again later.",
    }.get(stripe_code, "Payment gateway error occurred")

    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "error": "PaymentGatewayError",
            "message": user_message,
            "details": [
                {
                    "code": ErrorCode.STRIPE_API_ERROR,
                    "message": stripe_message if settings.app_env != "production" else user_message,
                }
            ],
            "remediation": REMEDIATION_HINTS.get(ErrorCode.STRIPE_API_ERROR),
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all other uncaught exceptions.

    Returns 500 Internal Server Error for unexpected exceptions.
    Logs full stack trace for debugging but returns safe error message to client.
    """
    from billing.schemas.error import ErrorCode
    from datetime import datetime
    import uuid
    import traceback

    request_id = request.headers.get("x-request-id", f"req_{uuid.uuid4().hex[:12]}")

    # Log full exception with stack trace
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        stack_trace=traceback.format_exc(),
    )

    # Return safe error message (don't expose internal details)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "details": [
                {
                    "code": ErrorCode.INTERNAL_ERROR,
                    "message": str(exc) if settings.debug else "Internal server error",
                }
            ],
            "remediation": "Please contact support with the request ID",
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "documentation_url": f"{request.base_url}docs",
        },
    )


# Root endpoint
@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "service": "Modern Subscription Billing Platform",
        "version": "0.1.0",
        "status": "operational",
        "docs": "/docs",
    }


# Include routers
from billing.api.v1 import health, accounts, plans, subscriptions, invoices, payments, usage, credits, webhook_endpoints

app.include_router(health.router, tags=["Health"])
app.include_router(accounts.router, prefix="/v1", tags=["Accounts"])
app.include_router(plans.router, prefix="/v1", tags=["Plans"])
app.include_router(subscriptions.router, prefix="/v1", tags=["Subscriptions"])
app.include_router(invoices.router, prefix="/v1", tags=["Invoices"])
app.include_router(payments.router, prefix="/v1", tags=["Payments"])
app.include_router(usage.router, prefix="/v1", tags=["Usage"])
app.include_router(credits.router, prefix="/v1", tags=["Credits"])
app.include_router(webhook_endpoints.router, prefix="/v1", tags=["Webhooks"])

# Additional routers will be added in subsequent phases
# from billing.api.v1 import credits, analytics
# ... other routers
