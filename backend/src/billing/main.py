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


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors with structured response."""
    logger.warning(
        "validation_error",
        path=request.url.path,
        method=request.method,
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": exc.errors(),
            "remediation": "Check the API documentation for correct request format",
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle database errors."""
    logger.error(
        "database_error",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "database_error",
            "message": "A database error occurred",
            "remediation": "Please try again later. Contact support if the problem persists",
        },
    )


@app.exception_handler(StripeError)
async def stripe_exception_handler(request: Request, exc: StripeError) -> JSONResponse:
    """Handle Stripe API errors."""
    logger.error(
        "stripe_error",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        stripe_code=getattr(exc, "code", None),
    )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "error": "payment_gateway_error",
            "message": "Payment gateway error occurred",
            "details": str(exc),
            "remediation": "Please try again. Contact support if the problem persists",
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other uncaught exceptions."""
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "remediation": "Please contact support with the request details",
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
from billing.api.v1 import health, accounts, plans, subscriptions, invoices, payments, usage, credits

app.include_router(health.router, tags=["Health"])
app.include_router(accounts.router, prefix="/v1", tags=["Accounts"])
app.include_router(plans.router, prefix="/v1", tags=["Plans"])
app.include_router(subscriptions.router, prefix="/v1", tags=["Subscriptions"])
app.include_router(invoices.router, prefix="/v1", tags=["Invoices"])
app.include_router(payments.router, prefix="/v1", tags=["Payments"])
app.include_router(usage.router, prefix="/v1", tags=["Usage"])
app.include_router(credits.router, prefix="/v1", tags=["Credits"])

# Additional routers will be added in subsequent phases
# from billing.api.v1 import credits, analytics
# ... other routers
