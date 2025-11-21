# Modern Subscription Billing Platform - Deployment Guide

Complete guide for deploying the Modern Subscription Billing Platform to production.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Local Development](#local-development)
4. [Production Deployment](#production-deployment)
5. [Post-Deployment](#post-deployment)
6. [Monitoring](#monitoring)
7. [Maintenance](#maintenance)

## Overview

The Modern Subscription Billing Platform is a cloud-native SaaS billing system with:

- **Backend API**: FastAPI (Python 3.11+) with REST and GraphQL
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **Background Workers**: ARQ for async tasks
- **Infrastructure**: Terraform for AWS/GCP
- **Compliance**: SOC2 and GDPR ready

## Prerequisites

### Required Tools

```bash
# Python 3.11+
python --version

# Docker
docker --version

# Terraform 1.5+
terraform version

# Cloud CLI (choose one or both)
aws --version
gcloud --version
```

### Required Accounts

- [ ] Cloud provider account (AWS or GCP)
- [ ] Stripe account for payment processing
- [ ] Domain name registered
- [ ] SSL certificate (ACM for AWS, auto-managed for GCP)

## Local Development

### 1. Setup Development Environment

```bash
# Clone repository
git clone https://github.com/your-org/killbill_modern.git
cd killbill_modern

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your local configuration
# Required variables:
# - DATABASE_URL
# - REDIS_URL
# - STRIPE_API_KEY
# - JWT_SECRET_KEY
```

### 3. Start Local Services

Using Docker Compose:

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Verify services are running
docker-compose ps
```

### 4. Run Database Migrations

```bash
# Run migrations
alembic upgrade head

# Seed test data (optional)
python scripts/seed_data.py
```

### 5. Start Development Server

```bash
# Start FastAPI development server
uvicorn billing.main:app --reload --port 8000

# API will be available at:
# - http://localhost:8000
# - Docs: http://localhost:8000/docs
# - GraphQL: http://localhost:8000/graphql
```

### 6. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=billing --cov-report=html

# Run specific test file
pytest tests/test_subscriptions.py -v
```

## Production Deployment

### Choose Cloud Provider

- **AWS**: ECS Fargate + RDS + ElastiCache (~$505/month)
- **GCP**: Cloud Run + Cloud SQL + Memorystore (~$648/month)

### AWS Deployment

#### 1. Build and Push Docker Image

```bash
# Build Docker image
cd backend
docker build -t billing-platform:v1.0.0 .

# Create ECR repository
aws ecr create-repository --repository-name billing-platform

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag billing-platform:v1.0.0 \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/billing-platform:v1.0.0

docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/billing-platform:v1.0.0
```

#### 2. Create ACM Certificate

```bash
# Request certificate
aws acm request-certificate \
  --domain-name billing.example.com \
  --validation-method DNS

# Follow DNS validation instructions in AWS Console
# Wait for certificate to be issued
```

#### 3. Deploy Infrastructure

```bash
cd terraform/aws

# Copy and edit configuration
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
# - Set db_password
# - Set ecr_repository_url
# - Set acm_certificate_arn
# - Adjust resource sizes for your needs

# Initialize Terraform
terraform init

# Review plan
terraform plan

# Deploy infrastructure
terraform apply
```

#### 4. Configure Secrets

```bash
# Update Stripe API key
aws secretsmanager put-secret-value \
  --secret-id billing-platform-stripe-api-key-production \
  --secret-string "sk_live_your_stripe_key"

# Update JWT secret
aws secretsmanager put-secret-value \
  --secret-id billing-platform-jwt-secret-production \
  --secret-string "your-jwt-secret-key-32-chars"
```

#### 5. Run Database Migrations

```bash
# Get RDS endpoint
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)

# Connect via bastion or ECS Exec
# Run migrations
alembic upgrade head
```

#### 6. Configure DNS

```bash
# Get ALB DNS name
ALB_DNS=$(terraform output -raw alb_dns_name)

# Create CNAME record in Route53
aws route53 change-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "billing.example.com",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "'$ALB_DNS'"}]
      }
    }]
  }'
```

### GCP Deployment

#### 1. Build and Push Docker Image

```bash
# Create Artifact Registry repository
gcloud artifacts repositories create billing-platform \
  --repository-format=docker \
  --location=us-central1

# Configure Docker authentication
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push
cd backend
docker build -t billing-platform:v1.0.0 .

docker tag billing-platform:v1.0.0 \
  us-central1-docker.pkg.dev/<project-id>/billing-platform/billing-platform:v1.0.0

docker push us-central1-docker.pkg.dev/<project-id>/billing-platform/billing-platform:v1.0.0
```

#### 2. Deploy Infrastructure

```bash
cd terraform/gcp

# Copy and edit configuration
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
# - Set project_id
# - Set db_password
# - Set artifact_registry_repo
# - Set domain_name
# - Adjust resource sizes

# Initialize Terraform
terraform init

# Review plan
terraform plan

# Deploy infrastructure
terraform apply
```

#### 3. Configure Secrets

```bash
# Update Stripe API key
echo -n "sk_live_your_stripe_key" | \
  gcloud secrets versions add billing-platform-stripe-api-key-production --data-file=-

# Update JWT secret
echo -n "your-jwt-secret-key-32-chars" | \
  gcloud secrets versions add billing-platform-jwt-secret-production --data-file=-
```

#### 4. Run Database Migrations

```bash
# Get Cloud SQL connection name
CONNECTION_NAME=$(terraform output -raw db_connection_name)

# Start Cloud SQL Proxy
cloud-sql-proxy $CONNECTION_NAME &

# Run migrations
alembic upgrade head
```

#### 5. Configure DNS

```bash
# Get Load Balancer IP
LB_IP=$(terraform output -raw lb_ip_address)

# Create A record
gcloud dns record-sets create billing.example.com. \
  --rrdatas=$LB_IP \
  --type=A \
  --ttl=300 \
  --zone=your-dns-zone

# Wait 10-30 minutes for SSL certificate to provision
```

## Post-Deployment

### 1. Verify Deployment

```bash
# Test health endpoint
curl https://billing.example.com/health

# Expected response:
# {"status": "healthy", "database": "connected", "redis": "connected"}
```

### 2. Test API Endpoints

```bash
# Create test account
curl -X POST https://billing.example.com/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "name": "Test Account",
    "currency": "USD"
  }'

# Get accounts
curl https://billing.example.com/v1/accounts

# Test GraphQL
curl -X POST https://billing.example.com/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ accounts(first: 10) { edges { node { id email name } } } }"
  }'
```

### 3. Set Up Monitoring Alerts

**AWS:**
```bash
# Create SNS topic for alerts
aws sns create-topic --name billing-platform-alerts

# Subscribe to email notifications
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:123456789:billing-platform-alerts \
  --protocol email \
  --notification-endpoint alerts@example.com
```

**GCP:**
```bash
# Create notification channel
gcloud alpha monitoring channels create \
  --display-name="Billing Platform Alerts" \
  --type=email \
  --channel-labels=email_address=alerts@example.com
```

### 4. Configure Webhooks

```bash
# Register Stripe webhook
stripe listen --forward-to https://billing.example.com/webhooks/stripe

# Or configure via Stripe Dashboard:
# - URL: https://billing.example.com/webhooks/stripe
# - Events: invoice.paid, invoice.payment_failed, customer.subscription.deleted, etc.
```

### 5. Enable Background Workers

```bash
# AWS ECS: Create worker service (similar to app service)
# GCP Cloud Run: Create scheduled Cloud Run jobs

# Or use separate worker instance:
arq billing.workers.analytics.WorkerSettings
```

## Monitoring

### Application Metrics

**Key Metrics to Monitor:**
- Request rate (requests/second)
- Response time (P50, P95, P99)
- Error rate (5xx errors)
- Database connections
- Cache hit rate
- Queue depth (background tasks)

**AWS CloudWatch:**
```bash
# View ECS metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=billing-platform-cluster-production \
  --start-time 2025-11-21T00:00:00Z \
  --end-time 2025-11-21T23:59:59Z \
  --period 300 \
  --statistics Average
```

**GCP Cloud Monitoring:**
```bash
# View Cloud Run metrics
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/request_count"' \
  --start-time=2025-11-21T00:00:00Z \
  --end-time=2025-11-21T23:59:59Z
```

### Business Metrics

Monitor via `/v1/analytics` endpoints:
- MRR (Monthly Recurring Revenue)
- Churn Rate
- Customer Lifetime Value (LTV)
- Active Subscriptions
- Failed Payments

### Logs

**AWS:**
```bash
# Tail application logs
aws logs tail /ecs/billing-platform-app-production --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /ecs/billing-platform-app-production \
  --filter-pattern "ERROR"
```

**GCP:**
```bash
# Tail application logs
gcloud run services logs tail billing-platform-app-production \
  --region=us-central1

# Search for errors
gcloud logging read \
  'resource.type="cloud_run_revision" AND severity="ERROR"' \
  --limit=50
```

## Maintenance

### Regular Tasks

**Daily:**
- [ ] Check monitoring dashboards for anomalies
- [ ] Review error logs
- [ ] Monitor payment processing success rate

**Weekly:**
- [ ] Review cost optimization opportunities
- [ ] Check for security updates
- [ ] Verify backup success

**Monthly:**
- [ ] Test disaster recovery procedures
- [ ] Review and update access controls
- [ ] Analyze performance trends
- [ ] Update dependencies

### Updating the Application

```bash
# Build new version
docker build -t billing-platform:v1.1.0 .

# Push to registry
docker push <registry>/billing-platform:v1.1.0

# Update deployment (zero-downtime)
# AWS:
aws ecs update-service \
  --cluster billing-platform-cluster-production \
  --service billing-platform-app-service-production \
  --force-new-deployment

# GCP:
gcloud run services update billing-platform-app-production \
  --image=us-central1-docker.pkg.dev/.../billing-platform:v1.1.0 \
  --region=us-central1
```

### Scaling

**Vertical Scaling (more resources per instance):**
```bash
# AWS: Update variables.tf and apply
app_cpu = "2048"  # 2 vCPU
app_memory = "4096"  # 4 GB

# GCP: Update variables.tf and apply
cloud_run_cpu = "4"
cloud_run_memory = "4Gi"
```

**Horizontal Scaling (more instances):**
```bash
# AWS: Update variables.tf
app_min_count = 4
app_max_count = 20

# GCP: Update variables.tf
cloud_run_min_instances = "4"
cloud_run_max_instances = "20"
```

### Backup and Restore

**Create Manual Backup:**
```bash
# AWS RDS
aws rds create-db-snapshot \
  --db-instance-identifier billing-platform-db-production \
  --db-snapshot-identifier manual-$(date +%Y%m%d)

# GCP Cloud SQL
gcloud sql backups create \
  --instance=billing-platform-db-production \
  --description="Manual backup $(date +%Y%m%d)"
```

**Restore from Backup:**
```bash
# AWS RDS
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier billing-platform-db-restored \
  --db-snapshot-identifier manual-20251121

# GCP Cloud SQL
gcloud sql backups restore BACKUP_ID \
  --backup-instance=billing-platform-db-production
```

## Troubleshooting

### Common Issues

**Database Connection Errors:**
1. Check security group/firewall rules
2. Verify database is running
3. Check credentials in Secrets Manager
4. Test network connectivity

**High Latency:**
1. Check database query performance
2. Review cache hit rate
3. Analyze slow endpoints in logs
4. Consider adding database indexes

**Failed Payments:**
1. Check Stripe webhook configuration
2. Verify Stripe API key
3. Review payment error logs
4. Test with Stripe test cards

**5xx Errors:**
1. Check application logs
2. Verify all services are healthy
3. Check database connections
4. Review recent deployments

## Security

### Best Practices

- ✅ Never commit secrets to version control
- ✅ Use environment variables for configuration
- ✅ Enable encryption at rest and in transit
- ✅ Regular security audits
- ✅ Keep dependencies updated
- ✅ Monitor for suspicious activity
- ✅ Implement rate limiting
- ✅ Use WAF for DDoS protection

### Compliance

**SOC2 Controls:**
- CC6.6: Encryption implementation
- CC7.2: Security monitoring
- CC8.1: Change management (IaC)

**GDPR Requirements:**
- Article 32: Data encryption
- Article 33: Breach detection
- Right to erasure implementation

## Support

For issues or questions:

1. Check logs and monitoring dashboards
2. Review documentation:
   - [Terraform AWS](terraform/aws/README.md)
   - [Terraform GCP](terraform/gcp/README.md)
3. Contact support team

## License

See LICENSE file for details.
