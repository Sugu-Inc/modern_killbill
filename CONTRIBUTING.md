# Contributing to Modern Subscription Billing Platform

Thank you for your interest in contributing to the Modern Subscription Billing Platform! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Testing Guidelines](#testing-guidelines)
- [Code Style](#code-style)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Project Structure](#project-structure)
- [Common Tasks](#common-tasks)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code:

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose
- PostgreSQL 14+
- Redis 7+
- Poetry for dependency management

### Initial Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourorg/killbill_modern.git
   cd killbill_modern
   ```

2. **Set up the backend**:
   ```bash
   cd backend

   # Install Poetry
   pip install poetry==1.7.1

   # Install dependencies
   poetry install

   # Activate virtual environment
   poetry shell
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your local configuration
   ```

4. **Start dependencies with Docker Compose**:
   ```bash
   docker-compose up -d postgres redis
   ```

5. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

6. **Start the development server**:
   ```bash
   uvicorn billing.main:app --reload --port 8000
   ```

7. **Verify installation**:
   ```bash
   curl http://localhost:8000/health
   ```

## Development Workflow

### Test-Driven Development (TDD)

We follow a strict TDD approach for all new features:

1. **Write tests first**: Before implementing any feature, write integration tests
2. **See tests fail**: Run tests and verify they fail for the right reasons
3. **Implement feature**: Write minimal code to make tests pass
4. **Refactor**: Improve code while keeping tests green
5. **Repeat**: Continue the cycle for each feature

### Example TDD Workflow

```bash
# 1. Create integration test
touch backend/tests/integration/test_new_feature.py

# 2. Write failing tests
# Edit test_new_feature.py with test cases

# 3. Run tests (should fail)
pytest backend/tests/integration/test_new_feature.py -v

# 4. Implement feature
# Edit backend/src/billing/services/new_feature.py

# 5. Run tests (should pass)
pytest backend/tests/integration/test_new_feature.py -v

# 6. Run full test suite
pytest backend/tests/ -v
```

## Testing Guidelines

### Test Organization

```
backend/tests/
├── unit/           # Unit tests for individual functions
├── integration/    # Integration tests for workflows
└── conftest.py     # Shared fixtures
```

### Writing Integration Tests

Integration tests should:
- Test complete workflows end-to-end
- Use the database (via fixtures)
- Be independent and isolated
- Clean up after themselves

**Example**:
```python
@pytest.mark.asyncio
async def test_complete_billing_workflow(db_session: AsyncSession) -> None:
    """Test full workflow: account → subscription → invoice → payment."""
    # Create account
    account = Account(email="test@example.com", name="Test User", currency="USD")
    db_session.add(account)
    await db_session.flush()

    # Create plan
    plan = Plan(name="Basic", price=1000, currency="USD", interval=PlanInterval.MONTH)
    db_session.add(plan)
    await db_session.flush()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription = await subscription_service.create_subscription(
        SubscriptionCreate(account_id=account.id, plan_id=plan.id, quantity=1)
    )
    await db_session.commit()

    # Assert subscription is active
    assert subscription.status == SubscriptionStatus.ACTIVE

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)

    # Assert invoice is correct
    assert invoice.total == 1000 + invoice.tax
```

### Running Tests

```bash
# Run all tests
pytest backend/tests/ -v

# Run specific test file
pytest backend/tests/integration/test_subscriptions.py -v

# Run with coverage
pytest backend/tests/ --cov=billing --cov-report=html

# Run specific test
pytest backend/tests/integration/test_subscriptions.py::test_create_subscription -v

# Run tests matching pattern
pytest backend/tests/ -k "invoice" -v
```

### Test Coverage Requirements

- **Minimum coverage**: 80% for all new code
- **Integration tests**: Required for all user-facing features
- **E2E tests**: Required for critical workflows

## Code Style

### Python Style Guide

We follow PEP 8 with some modifications:

- **Line length**: 120 characters (not 79)
- **Imports**: Group by stdlib, third-party, local
- **Type hints**: Required for all function signatures
- **Docstrings**: Google style for all public functions

### Linting and Formatting

```bash
# Run Ruff linter
ruff check .

# Auto-fix issues
ruff check . --fix

# Format code (if using black)
black backend/src backend/tests

# Type checking (if using mypy)
mypy backend/src
```

### Code Quality Checklist

Before submitting code, ensure:
- [ ] All tests pass
- [ ] Code coverage >= 80%
- [ ] No linting errors
- [ ] Type hints present
- [ ] Docstrings added
- [ ] No security vulnerabilities

## Commit Guidelines

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Build process or tooling changes

**Example**:
```
feat: Add subscription pause functionality

Implement subscription pause/resume with auto-resume on date.
Includes pause_subscription and resume_subscription service methods.

Closes #123
```

### Commit Best Practices

- Write clear, descriptive commit messages
- Keep commits atomic (one logical change per commit)
- Reference issue numbers in commit messages
- Use present tense ("Add feature" not "Added feature")

## Pull Request Process

### Before Submitting

1. **Create feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Write tests first** (TDD approach)

3. **Implement feature**

4. **Run full test suite**:
   ```bash
   pytest backend/tests/ -v
   ```

5. **Update documentation** if needed

6. **Commit changes** following commit guidelines

### Submitting Pull Request

1. **Push branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create PR** on GitHub with:
   - Clear title describing the change
   - Detailed description of what and why
   - Reference to related issues
   - Screenshots/examples if UI changes

3. **PR Description Template**:
   ```markdown
   ## Summary
   Brief description of the changes

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Testing
   - [ ] All tests pass
   - [ ] Added new tests
   - [ ] Manual testing completed

   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] Self-review completed
   - [ ] Comments added for complex code
   - [ ] Documentation updated
   - [ ] No new warnings generated

   ## Related Issues
   Closes #<issue-number>
   ```

### PR Review Process

- PRs require at least one approval
- Address all review comments
- Keep PR scope focused and small
- Respond to feedback promptly

## Project Structure

```
killbill_modern/
├── backend/
│   ├── src/billing/          # Application code
│   │   ├── api/              # API endpoints
│   │   ├── models/           # Database models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   ├── integrations/     # External integrations
│   │   ├── middleware/       # Middleware components
│   │   └── main.py           # Application entry point
│   ├── tests/                # Test suite
│   │   ├── unit/             # Unit tests
│   │   └── integration/      # Integration tests
│   ├── alembic/              # Database migrations
│   └── pyproject.toml        # Dependencies
├── k8s/                      # Kubernetes manifests
├── specs/                    # Feature specifications
└── README.md
```

## Common Tasks

### Adding a New API Endpoint

1. **Write integration test**:
   ```python
   # tests/integration/test_new_endpoint.py
   @pytest.mark.asyncio
   async def test_new_endpoint(db_session: AsyncSession):
       # Test implementation
       pass
   ```

2. **Create Pydantic schema**:
   ```python
   # src/billing/schemas/new_resource.py
   class NewResourceCreate(BaseModel):
       field1: str
       field2: int
   ```

3. **Implement service**:
   ```python
   # src/billing/services/new_service.py
   class NewService:
       async def create_resource(self, data: NewResourceCreate):
           # Implementation
           pass
   ```

4. **Create API endpoint**:
   ```python
   # src/billing/api/v1/new_endpoint.py
   @router.post("")
   async def create_resource(data: NewResourceCreate, db: AsyncSession = Depends(get_db)):
       service = NewService(db)
       result = await service.create_resource(data)
       await db.commit()
       return result
   ```

5. **Register router**:
   ```python
   # src/billing/main.py
   from billing.api.v1 import new_endpoint
   app.include_router(new_endpoint.router, prefix="/v1", tags=["NewResource"])
   ```

### Creating Database Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add new_table"

# Review generated migration file
# Edit alembic/versions/<timestamp>_add_new_table.py

# Apply migration
alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

### Adding Business Metrics

```python
# src/billing/metrics.py
from prometheus_client import Counter

new_metric_counter = Counter(
    'new_metric_total',
    'Description of the metric',
    ['label1', 'label2']
)

# In your service
new_metric_counter.labels(label1='value1', label2='value2').inc()
```

### Debugging

```bash
# Run with debugger
python -m pdb -m uvicorn billing.main:app

# View logs
tail -f logs/billing.log

# Database queries (in ipython)
from billing.database import get_db
async with get_db() as db:
    result = await db.execute(select(Account))
    accounts = result.scalars().all()
```

## Getting Help

- **Documentation**: Check `/docs` endpoint for API documentation
- **Issues**: Search existing issues before creating new ones
- **Discussions**: Use GitHub Discussions for questions
- **Slack**: Join our Slack channel (if available)

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Stripe API Reference](https://stripe.com/docs/api)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for contributing to the Modern Subscription Billing Platform! 🎉
