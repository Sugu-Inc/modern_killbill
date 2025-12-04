# killbill_modern

> **A modern Python rewrite of [Kill Bill](https://github.com/killbill/killbill)**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-143%2F143-success.svg)](backend/tests/)

A simplified, cloud-native subscription billing platform built with Python FastAPI, delivering 80% of business value with 50% of code complexity. This project reimagines Kill Bill's robust billing engine with modern architectural patterns, async-first design, and significantly reduced complexity.

## 🎯 Project Vision

**Rewrite Kill Bill in Modern Python** - Demonstrate that a production-ready subscription billing platform can be built with:
- 🚀 **50% less code complexity** compared to traditional Java implementations
- ⚡ **Async-first architecture** for better performance and resource utilization
- 🏗️ **Cloud-native design** ready for Kubernetes and serverless
- 📊 **Modern observability** with structured logging and OpenTelemetry
- 🔒 **Security-first** approach with comprehensive audit capabilities

## 📋 Disclaimer

**This is a demonstration/case study project.** It showcases modern architecture patterns and code reduction techniques. For production subscription billing needs, consider:
- The original [Kill Bill](https://github.com/killbill/killbill) project for full-featured enterprise billing
- Commercial alternatives like Stripe Billing, Chargebee, or Recurly
- This project as a reference implementation or starting point for custom solutions

This implementation focuses on core billing workflows and may not include all features required for enterprise deployments.

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/abhi-sugu/killbill_modern.git
cd killbill_modern/backend

# Start infrastructure (PostgreSQL, Redis)
docker-compose up -d

# Install dependencies
poetry install

# Run tests (all 143 tests)
poetry run pytest

# Start the server
poetry run uvicorn billing.main:app --reload

# Access the API
open http://localhost:8000/docs
```

See the [backend README](backend/README.md) for detailed setup instructions.

## ✨ Key Features

### Core Billing Capabilities
- ✅ **Account Management** - Zero-friction account creation and lifecycle management
- 💳 **Flexible Pricing** - Monthly/annual plans, trials, usage-based billing
- 📄 **Smart Invoicing** - Automatic generation with proration and tax calculation
- 💰 **Payment Processing** - Stripe integration with retry logic and dunning
- 🌍 **Multi-Currency** - Bill customers in 20+ currencies
- 📊 **Analytics** - Pre-calculated MRR, churn, and LTV metrics
- 🔔 **Webhooks** - Real-time event notifications
- 🔐 **Security** - RBAC, audit logging, rate limiting

### Modern Architecture
- ⚡ **Async-First** - FastAPI with async SQLAlchemy for maximum performance
- 🏗️ **Microservices-Ready** - Clear service boundaries and REST APIs
- 📈 **Observable** - Structured logging, Prometheus metrics, OpenTelemetry traces
- 🔄 **Event-Driven** - ARQ for background jobs and async task processing
- 🧪 **Well-Tested** - 143 integration tests with 56% code coverage

## 📊 Kill Bill vs killbill_modern

| Aspect | Kill Bill (Original) | killbill_modern |
|--------|---------------------|-----------------|
| **Language** | Java | Python 3.11+ |
| **Framework** | Spring/JAX-RS | FastAPI (async) |
| **Database** | MySQL (primary) | PostgreSQL (primary) |
| **Architecture** | Plugin-based monolith | Simplified microservices |
| **Lines of Code** | ~100K+ | ~5K (50% reduction) |
| **Async Support** | Limited | Native async/await |
| **Setup Complexity** | High (Java ecosystem) | Low (pip/poetry) |
| **Cloud-Native** | Requires adaptation | Built-in support |
| **Learning Curve** | Steep | Moderate |

## 🏗️ Project Structure

```
killbill_modern/
├── backend/              # FastAPI application
│   ├── src/billing/      # Main application code
│   │   ├── api/          # REST endpoints (v1)
│   │   ├── services/     # Business logic
│   │   ├── models/       # Database models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── workers/      # Background jobs
│   │   ├── auth/         # Authentication & RBAC
│   │   └── integrations/ # Stripe, tax services
│   ├── tests/            # Integration tests (143)
│   ├── alembic/          # Database migrations
│   ├── SECURITY.md       # Security audit (783 lines)
│   └── README.md         # Detailed backend docs
├── specs/                # Feature specifications
├── terraform/            # Infrastructure as code
└── LICENSE               # Apache License 2.0
```

## 🔒 Security

Comprehensive security audit available in [SECURITY.md](backend/SECURITY.md):
- ✅ 11 implemented security controls
- ⚠️ 2 critical issues to address before production
- 📋 Complete pre-production security checklist
- 🛡️ SOC2, PCI DSS, and GDPR compliance guidance

**Key Security Features**:
- RS256 JWT authentication (15-minute expiry)
- 4-tier RBAC (Super Admin → Finance Viewer)
- Rate limiting (1000 req/hour)
- Security event monitoring
- OWASP security headers
- Audit logging

## 📖 Documentation

- **[Backend README](backend/README.md)** - Detailed setup and API documentation
- **[Security Audit](backend/SECURITY.md)** - Comprehensive security review
- **[API Docs](http://localhost:8000/docs)** - Interactive Swagger UI (when running)
- **[Feature Specs](specs/)** - Detailed feature specifications

## 🧪 Testing

```bash
cd backend

# Run all 143 tests
poetry run pytest

# With coverage report
poetry run pytest --cov=src/billing --cov-report=html

# Run specific test suite
poetry run pytest tests/integration/test_subscriptions.py -v
```

**Current Status**: ✅ 143/143 tests passing (100%)

## 🛠️ Tech Stack

| Category | Technology |
|----------|-----------|
| **Runtime** | Python 3.11+ |
| **Web Framework** | FastAPI (async) |
| **Database** | PostgreSQL 15+ |
| **Cache/Queue** | Redis 7+ |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Payments** | Stripe SDK |
| **Background Jobs** | ARQ (async Redis queue) |
| **Migrations** | Alembic |
| **Testing** | pytest, pytest-asyncio |
| **Observability** | structlog, Prometheus, OpenTelemetry |
| **Validation** | Pydantic V2 |

## 🎓 Learning Resources

This project serves as a practical case study for:
- Building production-ready billing systems
- FastAPI async patterns and best practices
- SQLAlchemy 2.0 async ORM usage
- Stripe integration patterns
- Event-driven architecture with Redis
- Comprehensive testing strategies
- Security hardening for financial systems

## 🤝 Acknowledgments

This project is inspired by [Kill Bill](https://github.com/killbill/killbill), the open-source subscription billing and payments platform. We're grateful to the Kill Bill community for pioneering open-source billing solutions and demonstrating that complex financial systems can be built as open-source software.

**Why a Rewrite?**
- Explore modern Python async patterns
- Reduce complexity while maintaining core functionality
- Demonstrate cloud-native architecture
- Provide a Python alternative for teams preferring Python over Java

## 📄 License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

This project is licensed under the same license as Kill Bill to maintain compatibility with the open-source billing ecosystem.

## 🔗 Links

- **Original Kill Bill**: https://github.com/killbill/killbill
- **Kill Bill Documentation**: https://docs.killbill.io/
- **This Project**: https://github.com/abhi-sugu/killbill_modern

## 💬 Contributing

This is a demonstration project. For production billing solutions, please contribute to the original [Kill Bill project](https://github.com/killbill/killbill).

For issues or questions about this implementation, please open an issue on GitHub.

---

**Built with ❤️ using Python, FastAPI, and modern cloud-native patterns**
