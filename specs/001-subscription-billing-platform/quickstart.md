# Quickstart: Local Development Setup

**Time to First Request**: < 5 minutes
**Platform**: Linux, macOS, Windows (via WSL2)
**Plan**: [plan.md](./plan.md)

## Prerequisites

- **Docker** 20.10+ and **Docker Compose** 2.0+
- **Python** 3.11+ (for running without Docker)
- **Git** 2.x+

## Quick Start (Docker Compose)

### 1. Clone and Start Services

```bash
# Clone repository
git clone https://github.com/yourorg/killbill_modern.git
cd killbill_modern

# Start all services (PostgreSQL, Redis, API, Worker)
docker-compose up -d

# Check service health
docker-compose ps
```

**Services**:
- `postgres`: PostgreSQL 15 (port 5432)
- `redis`: Redis 7 (port 6379)
- `api`: FastAPI application (port 8000)
- `worker`: ARQ background worker

### 2. Run Database Migrations

```bash
# Apply migrations
docker-compose exec api alembic upgrade head

# Seed test data (optional)
docker-compose exec api python scripts/seed_test_data.py
```

### 3. Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "database": "connected", "redis": "connected"}

# API documentation
open http://localhost:8000/docs  # OpenAPI UI
open http://localhost:8000/graphql  # GraphQL playground
```

---

## Local Development (Without Docker)

### 1. Install Dependencies

```bash
# Install Poetry (Python dependency manager)
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install

# Activate virtual environment
poetry shell
```

### 2. Start Dependencies

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Or use system services
brew install postgresql@15 redis  # macOS
brew services start postgresql@15
brew services start redis
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
# DATABASE_URL=postgresql://billing:billing@localhost:5432/billing
# REDIS_URL=redis://localhost:6379/0
# STRIPE_API_KEY=sk_test_...
# STRIPE_WEBHOOK_SECRET=whsec_...
# JWT_PUBLIC_KEY=...
```

### 4. Run Migrations

```bash
# Create database
createdb billing

# Run migrations
alembic upgrade head

# Seed test data
python scripts/seed_test_data.py
```

### 5. Start Application

```bash
# Terminal 1: API server
uvicorn billing.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Background worker
arq billing.workers.WorkerSettings

# Terminal 3: (Optional) Watch logs
tail -f logs/billing.log
```

---

## Example API Requests

### 1. Create Account

```bash
curl -X POST http://localhost:8000/v1/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "name": "Acme Corporation",
    "currency": "USD",
    "timezone": "America/New_York"
  }'
```

**Response**:
```json
{
  "id": "acc_1A2B3C4D5E6F",
  "email": "customer@example.com",
  "name": "Acme Corporation",
  "currency": "USD",
  "timezone": "America/New_York",
  "tax_exempt": false,
  "metadata": {},
  "created_at": "2025-11-19T12:00:00Z",
  "updated_at": "2025-11-19T12:00:00Z"
}
```

### 2. Create Plan

```bash
curl -X POST http://localhost:8000/v1/plans \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Pro Plan",
    "interval": "month",
    "amount": 9900,
    "currency": "USD",
    "trial_days": 14,
    "usage_type": "licensed"
  }'
```

### 3. Add Payment Method

```bash
# First, create a Stripe payment method token (use Stripe.js or test mode)
TOKEN="pm_card_visa"  # Stripe test token

curl -X POST http://localhost:8000/v1/accounts/acc_1A2B3C4D5E6F/payment-methods \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_method_token": "pm_card_visa",
    "set_as_default": true
  }'
```

### 4. Create Subscription

```bash
curl -X POST http://localhost:8000/v1/subscriptions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_1A2B3C4D5E6F",
    "plan_id": "plan_XYZ",
    "quantity": 5
  }'
```

**Response**:
```json
{
  "id": "sub_ABC123",
  "account_id": "acc_1A2B3C4D5E6F",
  "plan_id": "plan_XYZ",
  "status": "TRIAL",
  "quantity": 5,
  "current_period_start": "2025-11-19T12:00:00Z",
  "current_period_end": "2025-12-19T12:00:00Z",
  "trial_end": "2025-12-03T12:00:00Z",
  "created_at": "2025-11-19T12:00:00Z"
}
```

### 5. Record Usage

```bash
curl -X POST http://localhost:8000/v1/usage \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscription_id": "sub_ABC123",
    "metric": "api_calls",
    "quantity": 1500,
    "timestamp": "2025-11-19T12:00:00Z",
    "idempotency_key": "usage_2025_11_19_12_00"
  }'
```

### 6. Retrieve MRR Analytics

```bash
curl -X GET http://localhost:8000/v1/analytics/mrr \
  -H "Authorization: Bearer $TOKEN"
```

---

## GraphQL Examples

### 1. Query Account with Nested Data

```graphql
query GetAccountDetails {
  account(id: "acc_1A2B3C4D5E6F") {
    email
    name
    creditBalance(currency: "USD")
    subscriptions(status: ACTIVE) {
      edges {
        node {
          id
          status
          quantity
          plan {
            name
            amount
            interval
          }
          invoices(limit: 5) {
            edges {
              node {
                number
                amountDue
                status
                dueDate
              }
            }
          }
        }
      }
    }
  }
}
```

**Run with curl**:
```bash
curl -X POST http://localhost:8000/graphql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query { account(id: \"acc_1A2B3C4D5E6F\") { email name } }"
  }'
```

### 2. Subscribe to Real-time Updates

```javascript
// WebSocket subscription (GraphQL Subscription)
const ws = new WebSocket('ws://localhost:8000/graphql');

ws.send(JSON.stringify({
  type: 'subscribe',
  payload: {
    query: `
      subscription {
        invoiceUpdates(accountId: "acc_1A2B3C4D5E6F") {
          id
          number
          status
          amountDue
        }
      }
    `
  }
}));

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Invoice update:', data.payload.data.invoiceUpdates);
};
```

---

## Testing

### Run Tests

```bash
# All tests
poetry run pytest

# Unit tests only
poetry run pytest tests/services/

# Integration tests (require DB)
poetry run pytest tests/integration/

# With coverage
poetry run pytest --cov=billing --cov-report=html

# Watch mode (auto-rerun on file changes)
poetry run ptw
```

### Test Fixtures

Test database is automatically created and torn down:

```python
# tests/conftest.py provides fixtures:
# - db: Test database session
# - client: TestClient for API requests
# - account_factory: Create test accounts
# - subscription_factory: Create test subscriptions

def test_create_subscription(client, account_factory, plan_factory):
    account = account_factory(email="test@example.com")
    plan = plan_factory(amount=9900)

    response = client.post("/v1/subscriptions", json={
        "account_id": str(account.id),
        "plan_id": str(plan.id),
        "quantity": 2
    })

    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 2
    assert data["status"] == "TRIAL"
```

---

## Database Management

### Create Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add proration_behavior column"

# Edit migration file in alembic/versions/

# Apply migration
alembic upgrade head
```

### Rollback Migration

```bash
# Rollback last migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade abc123
```

### Reset Database

```bash
# Drop all tables and recreate
alembic downgrade base
alembic upgrade head
python scripts/seed_test_data.py
```

---

## Stripe Integration (Test Mode)

### Setup Test Keys

1. Create Stripe account at https://dashboard.stripe.com/register
2. Get test API keys from https://dashboard.stripe.com/test/apikeys
3. Add to `.env`:
   ```
   STRIPE_API_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

### Test Payment Methods

Stripe provides test cards:

- **Success**: `pm_card_visa` or `4242 4242 4242 4242`
- **Decline**: `pm_card_chargeDecline` or `4000 0000 0000 0002`
- **Insufficient Funds**: `4000 0000 0000 9995`

### Webhook Testing (Local)

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:8000/v1/webhooks/stripe

# Trigger test events
stripe trigger invoice.payment_succeeded
stripe trigger payment_intent.succeeded
```

---

## Troubleshooting

### Database Connection Errors

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check connection
psql postgresql://billing:billing@localhost:5432/billing

# View logs
docker-compose logs postgres
```

### Redis Connection Errors

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
redis-cli ping  # Should return PONG

# View logs
docker-compose logs redis
```

### API Server Errors

```bash
# View logs
docker-compose logs api

# Check dependencies
poetry show

# Rebuild Docker image
docker-compose build api
docker-compose up -d api
```

### Worker Not Processing Jobs

```bash
# Check worker logs
docker-compose logs worker

# Manually enqueue test job
poetry run python -c "
from billing.workers import billing_cycle
from arq import create_pool
import asyncio

async def test():
    redis = await create_pool()
    job = await redis.enqueue_job('generate_invoice', 'sub_ABC123')
    print(f'Job queued: {job.job_id}')

asyncio.run(test())
"
```

---

## Next Steps

1. ✅ Local environment running
2. ⏭️ Review [data-model.md](./data-model.md) for database schema
3. ⏭️ Review [contracts/openapi.yaml](./contracts/openapi.yaml) for API reference
4. ⏭️ Run `/speckit.tasks` to generate implementation tasks
5. ⏭️ Start implementing features from tasks.md

## Resources

- **API Documentation**: http://localhost:8000/docs
- **GraphQL Playground**: http://localhost:8000/graphql
- **Data Model**: [data-model.md](./data-model.md)
- **OpenAPI Spec**: [contracts/openapi.yaml](./contracts/openapi.yaml)
- **GraphQL Schema**: [contracts/schema.graphql](./contracts/schema.graphql)
- **Webhook Events**: [contracts/webhooks.yaml](./contracts/webhooks.yaml)

## Support

- Report issues: GitHub Issues
- Development docs: `docs/` directory
- Team chat: #billing-platform channel
