# Modern Subscription Billing Platform

A simplified, cloud-native subscription billing platform built with Python FastAPI, delivering 80% of business value with 50% of code complexity.

## Features

- **Account Management**: Zero-friction account creation with optional payment methods
- **Flexible Pricing**: Monthly/annual plans with trials and usage-based billing
- **Smart Invoicing**: Automatic invoice generation with proration and tax calculation
- **Payment Processing**: Stripe integration with automatic retries and dunning
- **Multi-Currency Support**: Bill customers in 20+ currencies
- **Real-Time Webhooks**: Event notifications for all billing state changes
- **Analytics**: Pre-calculated MRR, churn, and LTV metrics
- **Production-Ready**: 99.9% uptime, comprehensive observability, RBAC

## Tech Stack

- **Runtime**: Python 3.11+
- **Web Framework**: FastAPI (async-first)
- **Database**: PostgreSQL 15+
- **Cache/Queue**: Redis 7+
- **Payments**: Stripe SDK
- **Observability**: structlog, Prometheus, OpenTelemetry
- **Testing**: pytest, pytest-asyncio

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Poetry (Python package manager)

### Local Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd killbill_modern/backend
   ```

2. **Start infrastructure services**:
   ```bash
   docker-compose up -d
   ```

3. **Install dependencies**:
   ```bash
   poetry install
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Run database migrations**:
   ```bash
   poetry run alembic upgrade head
   ```

6. **Start the development server**:
   ```bash
   poetry run uvicorn billing.main:app --reload --host 0.0.0.0 --port 8000
   ```

7. **Access the API**:
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health
   - Metrics: http://localhost:8000/metrics

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src/billing --cov-report=html

# Run specific test file
poetry run pytest tests/integration/test_accounts.py

# Run with verbose output
poetry run pytest -v -s
```

### Code Quality

```bash
# Format code
poetry run black src tests

# Lint code
poetry run ruff check src tests

# Type checking
poetry run mypy src
```

## Project Structure

```
backend/
├── src/billing/
│   ├── main.py              # FastAPI application entry
│   ├── config.py            # Settings management
│   ├── database.py          # Database session
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic schemas
│   ├── api/                 # REST endpoints
│   │   ├── v1/              # API version 1
│   │   └── webhooks/        # Webhook handlers
│   ├── services/            # Business logic
│   ├── integrations/        # External services (Stripe, tax)
│   ├── workers/             # Background jobs (ARQ)
│   ├── middleware/          # Custom middleware
│   ├── auth/                # Authentication & authorization
│   └── utils/               # Shared utilities
├── tests/
│   ├── integration/         # API endpoint tests
│   ├── services/            # Business logic tests
│   └── utils/               # Utility tests
├── alembic/                 # Database migrations
├── pyproject.toml           # Dependencies & config
└── docker-compose.yml       # Local dev services
```

## API Documentation

Once the server is running, visit http://localhost:8000/docs for interactive API documentation powered by Swagger UI.

### Core Endpoints

- `POST /v1/accounts` - Create account
- `GET /v1/accounts/{id}` - Get account details
- `POST /v1/plans` - Create pricing plan
- `POST /v1/subscriptions` - Create subscription
- `GET /v1/invoices` - List invoices
- `POST /v1/usage` - Submit usage events
- `GET /v1/analytics/mrr` - Get MRR metrics

## Database Migrations

```bash
# Create a new migration
poetry run alembic revision --autogenerate -m "description"

# Apply migrations
poetry run alembic upgrade head

# Rollback last migration
poetry run alembic downgrade -1

# View migration history
poetry run alembic history
```

## Background Workers

Background jobs are handled by ARQ (async Redis queue):

```bash
# Start ARQ worker
poetry run arq billing.workers.WorkerSettings
```

Workers handle:
- Billing cycle processing (invoice generation)
- Payment retries
- Dunning process
- Usage finalization
- Webhook delivery
- Analytics calculation

## Monitoring & Observability

### Health Checks

- **Liveness**: `GET /health` - Basic health check
- **Readiness**: `GET /health/ready` - Check DB, Redis, Stripe connectivity

### Metrics

Prometheus metrics exposed at `GET /metrics`:
- `api_request_duration_seconds` - API latency histogram
- `api_errors_total` - Error rate counter
- `invoices_generated_total` - Business metric
- `payments_attempted_total{status}` - Payment success/failure
- `mrr_dollars` - Monthly recurring revenue gauge

### Logging

Structured JSON logs via structlog with request context:
```json
{
  "event": "payment_processed",
  "request_id": "abc123",
  "invoice_id": "inv_xxx",
  "amount": 9900,
  "status": "success",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Distributed Tracing

OpenTelemetry instrumentation for FastAPI and SQLAlchemy tracks request flow across services.

## Configuration

Key environment variables (see `.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `REDIS_URL` | Redis connection string | - |
| `STRIPE_SECRET_KEY` | Stripe API secret key | - |
| `LOG_LEVEL` | Logging level | INFO |
| `JWT_SECRET_KEY` | JWT signing key | - |
| `RATE_LIMIT_PER_HOUR` | API rate limit | 1000 |

## Security

- **Authentication**: JWT with RS256 signing
- **Authorization**: RBAC with 4 roles (Super Admin, Billing Admin, Support Rep, Finance Viewer)
- **Rate Limiting**: 1000 requests/hour per API key
- **Audit Logging**: All create/update/delete operations logged
- **Data Retention**: Automated cleanup of old audit logs (3 years)

## Deployment

### Docker

```bash
docker build -t billing-api .
docker run -p 8000:8000 --env-file .env billing-api
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

Includes:
- Deployment with liveness/readiness probes
- Service with load balancer
- Ingress for external access
- ConfigMap for configuration
- Prometheus scraping annotations

## Performance Targets

- **Uptime**: 99.9% (43 minutes downtime/month)
- **API Latency**: <200ms p95
- **Database Reads**: <50ms p99
- **Invoice Generation**: 100/second sustained
- **Usage Ingestion**: 10,000 events/minute
- **Scale**: 100,000 active subscriptions

## License

Proprietary - All rights reserved

## Support

For issues and questions, contact the platform team.
