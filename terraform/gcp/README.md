# GCP Infrastructure - Modern Subscription Billing Platform

Production-ready Terraform configuration for deploying the Modern Subscription Billing Platform on Google Cloud Platform.

## Architecture Overview

```
Internet
    |
    v
Cloud Load Balancer (HTTPS)
    |
    v
Cloud Run (Auto-scaling 2-10 instances)
    |
    +-- VPC Access Connector
    |
    v
Cloud SQL PostgreSQL 15 (Regional HA, Encrypted)
    |
    v
Memorystore Redis 7 (HA, Encrypted)
```

## Infrastructure Components

### Networking
- **VPC** with custom subnet
- **Cloud NAT** for outbound internet access
- **VPC Access Connector** for Cloud Run to access VPC resources
- **Firewall Rules** for internal communication and health checks

### Compute
- **Cloud Run** serverless containers with auto-scaling (2-10 instances)
- **Cloud Load Balancer** with HTTPS termination and automatic SSL certificate
- Request-based and CPU-based auto-scaling

### Data Storage
- **Cloud SQL PostgreSQL 15** with:
  - Regional HA deployment (multi-zone)
  - Automated backups (30-day retention)
  - Point-in-time recovery (7 days)
  - Encryption at rest with Cloud KMS
  - Query Insights enabled
- **Memorystore Redis 7** with:
  - Standard HA tier (automatic failover)
  - Encryption at rest and in transit
  - RDB persistence snapshots

### Security
- **Cloud KMS** encryption keys with automatic rotation (90 days)
- **Secret Manager** for sensitive data (DB password, Stripe API key, JWT secret)
- **Service Accounts** with least-privilege IAM permissions
- **SSL/TLS** encryption in transit

### Monitoring
- **Cloud Logging** for application and infrastructure logs
- **Cloud Monitoring** alerts for:
  - High error rates (5xx errors)
  - High latency (P95 > 1s)
  - Database CPU utilization > 80%
- **Cloud Run Request Metrics** for performance tracking

## Prerequisites

1. **gcloud CLI** configured with appropriate credentials
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Terraform** 1.5 or later
   ```bash
   terraform version
   ```

3. **GCP Project** with billing enabled
   ```bash
   gcloud projects create billing-platform-prod
   gcloud beta billing projects link billing-platform-prod \
     --billing-account=BILLING_ACCOUNT_ID
   ```

4. **Artifact Registry Repository** for Docker images
   ```bash
   gcloud artifacts repositories create billing-platform \
     --repository-format=docker \
     --location=us-central1 \
     --description="Billing platform Docker images"
   ```

5. **GCS Bucket** for Terraform state (create manually or comment out backend in main.tf)
   ```bash
   gcloud storage buckets create gs://billing-platform-terraform-state \
     --location=us-central1 \
     --uniform-bucket-level-access

   gcloud storage buckets update gs://billing-platform-terraform-state \
     --versioning
   ```

6. **Enable Required APIs** (Terraform will enable these automatically)
   ```bash
   gcloud services enable \
     compute.googleapis.com \
     run.googleapis.com \
     sqladmin.googleapis.com \
     redis.googleapis.com \
     secretmanager.googleapis.com \
     cloudkms.googleapis.com
   ```

## Deployment Steps

### 1. Configure Variables

Copy the example variables file and customize:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set:
- `project_id` - Your GCP project ID
- `db_password` - Strong database password
- `artifact_registry_repo` - Your Artifact Registry repository URL
- `domain_name` - Your domain name for SSL certificate
- Other environment-specific values

**Security Note**: Never commit `terraform.tfvars` to version control. Set sensitive values via environment variables:

```bash
export TF_VAR_db_password="your-strong-password"
export TF_VAR_project_id="your-gcp-project-id"
```

### 2. Build and Push Docker Image

```bash
# Authenticate with Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build the Docker image
cd ../../backend
docker build -t billing-platform:v1.0.0 .

# Tag and push
docker tag billing-platform:v1.0.0 \
  us-central1-docker.pkg.dev/YOUR_PROJECT_ID/billing-platform/billing-platform:v1.0.0

docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/billing-platform/billing-platform:v1.0.0
```

### 3. Initialize Terraform

```bash
cd terraform/gcp
terraform init
```

### 4. Review Planned Changes

```bash
terraform plan
```

Review the output to ensure all resources are configured correctly.

### 5. Apply Configuration

```bash
terraform apply
```

Type `yes` when prompted to create the resources.

**Deployment time**: Approximately 10-15 minutes.

### 6. Store Secrets in Secret Manager

After infrastructure is created, update secrets:

```bash
# Update Stripe API key
echo -n "sk_live_your_stripe_key" | \
  gcloud secrets versions add billing-platform-stripe-api-key-production --data-file=-

# Update JWT secret
echo -n "your-jwt-secret-key" | \
  gcloud secrets versions add billing-platform-jwt-secret-production --data-file=-
```

### 7. Run Database Migrations

Connect to Cloud SQL and run Alembic migrations:

```bash
# Get Cloud SQL connection name
CONNECTION_NAME=$(terraform output -raw db_connection_name)

# Run migrations using Cloud SQL Proxy
cloud-sql-proxy $CONNECTION_NAME &
alembic upgrade head
```

### 8. Configure DNS

Point your domain to the Load Balancer IP:

```bash
# Get Load Balancer IP
LB_IP=$(terraform output -raw lb_ip_address)

# Create A record in Cloud DNS
gcloud dns record-sets create billing.example.com. \
  --rrdatas=$LB_IP \
  --type=A \
  --ttl=300 \
  --zone=YOUR_DNS_ZONE
```

**Note**: SSL certificate provisioning takes 10-30 minutes after DNS is configured.

### 9. Verify Deployment

Test the API:

```bash
# Wait for SSL certificate to be provisioned
curl https://billing.example.com/health
```

## Terraform Outputs

After deployment, useful outputs:

```bash
# Get all outputs
terraform output

# Specific outputs
terraform output vpc_id
terraform output db_connection_name
terraform output redis_host
terraform output lb_ip_address
terraform output cloud_run_url
```

## Scaling

### Auto-Scaling

Cloud Run auto-scales automatically based on:
- **Request volume** (default: 80 concurrent requests per instance)
- **CPU utilization**
- **Min instances**: 2 (configurable)
- **Max instances**: 10 (configurable)

Adjust in `variables.tf`:
```hcl
variable "cloud_run_min_instances" {
  default = "2"
}

variable "cloud_run_max_instances" {
  default = "10"
}
```

### Manual Scaling

Force minimum instances:

```bash
gcloud run services update billing-platform-app-production \
  --region=us-central1 \
  --min-instances=5
```

## Monitoring and Logging

### Cloud Logging

View application logs:

```bash
# Real-time logs
gcloud run services logs tail billing-platform-app-production \
  --region=us-central1

# Query logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=billing-platform-app-production" \
  --limit=50 \
  --format=json
```

### Cloud Monitoring

View metrics in Cloud Console:
- Navigation Menu → Monitoring → Dashboards
- Filter by "Cloud Run" or "Cloud SQL"

Create custom dashboard:

```bash
gcloud monitoring dashboards create --config-from-file=dashboard.yaml
```

### Alert Policies

View active alerts:

```bash
gcloud alpha monitoring policies list
```

## Backup and Recovery

### Cloud SQL Backups

- **Automated backups**: 30-day retention (configurable)
- **Backup window**: 03:00-04:00 UTC
- **Point-in-time recovery**: 7-day transaction log retention

Create manual backup:

```bash
gcloud sql backups create \
  --instance=billing-platform-db-production \
  --description="Manual backup $(date +%Y%m%d)"
```

Restore from backup:

```bash
# List backups
gcloud sql backups list --instance=billing-platform-db-production

# Restore from backup
gcloud sql backups restore BACKUP_ID \
  --backup-instance=billing-platform-db-production \
  --backup-id=BACKUP_ID
```

Point-in-time recovery:

```bash
gcloud sql backups restore BACKUP_ID \
  --backup-instance=billing-platform-db-production \
  --point-in-time="2025-11-21T12:00:00Z"
```

### Memorystore Backups

- **Automated snapshots**: RDB snapshots every hour
- **Export to GCS**:

```bash
gcloud redis instances export \
  billing-platform-redis-production \
  gs://billing-platform-backups/redis/$(date +%Y%m%d).rdb \
  --region=us-central1
```

## Cost Optimization

### Production Cost Estimate (us-central1)

| Resource | Configuration | Monthly Cost (approx) |
|----------|--------------|----------------------|
| Cloud SQL | db-custom-2-7680, 100GB, HA | $280 |
| Memorystore Redis | 4GB, Standard HA | $200 |
| Cloud Run | 2 vCPU, 2GB RAM (avg usage) | $120 |
| Load Balancer | Standard | $18 |
| Cloud KMS | Key storage + operations | $5 |
| Cloud Logging | 50GB ingestion | $25 |
| **Total** | | **~$648/month** |

### Cost Reduction Strategies

1. **Use Committed Use Discounts** for predictable workloads (up to 57% savings)
2. **Scale down non-production environments**:
   ```bash
   # Stop Cloud SQL instance during off-hours
   gcloud sql instances patch billing-platform-db-staging --no-activation-policy
   ```
3. **Optimize log retention** (reduce to 7 days for dev/staging)
4. **Use Cloud Run min-instances=0** for development environments
5. **Use BASIC tier Redis** for non-production

### Enable Cost Controls

Set budget alerts:

```bash
gcloud billing budgets create \
  --billing-account=BILLING_ACCOUNT_ID \
  --display-name="Billing Platform Budget" \
  --budget-amount=1000USD \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=90
```

## Security Best Practices

### Implemented

✅ Encryption at rest (Cloud SQL, Memorystore, Secret Manager)
✅ Encryption in transit (TLS 1.3, Cloud SQL SSL)
✅ Least-privilege service accounts
✅ KMS key rotation (90 days)
✅ Regional HA deployments
✅ Automated backups
✅ VPC isolation

### Additional Recommendations

- [ ] Enable VPC Service Controls for data exfiltration protection
- [ ] Configure Cloud Armor for DDoS protection
- [ ] Enable Security Command Center
- [ ] Implement Binary Authorization for container image verification
- [ ] Configure Cloud Audit Logs
- [ ] Enable secrets rotation with Cloud Functions

## Troubleshooting

### Common Issues

#### 1. Cloud Run Service Not Starting

Check logs:
```bash
gcloud run services logs read billing-platform-app-production \
  --region=us-central1 \
  --limit=50
```

Common causes:
- Invalid environment variables
- Cannot pull image from Artifact Registry
- Health check failures
- Cloud SQL connection issues

#### 2. Database Connection Errors

Verify VPC Access Connector:
```bash
gcloud compute networks vpc-access connectors describe \
  billing-platform-connector-production \
  --region=us-central1
```

Test Cloud SQL connectivity:
```bash
gcloud sql connect billing-platform-db-production --user=billing_admin
```

#### 3. SSL Certificate Not Provisioning

Check certificate status:
```bash
gcloud compute ssl-certificates describe \
  billing-platform-lb-cert-production \
  --global
```

Requirements:
- DNS must point to Load Balancer IP
- Can take 10-30 minutes to provision

#### 4. High Cloud SQL CPU

Enable Query Insights:
```bash
gcloud sql instances patch billing-platform-db-production \
  --insights-config-query-insights-enabled
```

View slow queries in Cloud Console:
- Cloud SQL → Instance → Query Insights

## Updating Infrastructure

### Update Application Version

1. Build and push new Docker image
2. Update Cloud Run service:

```bash
gcloud run services update billing-platform-app-production \
  --image=us-central1-docker.pkg.dev/PROJECT_ID/billing-platform/billing-platform:v1.1.0 \
  --region=us-central1
```

Cloud Run handles rolling updates automatically with zero downtime.

### Modify Infrastructure

1. Update `variables.tf` or `terraform.tfvars`
2. Review changes:
   ```bash
   terraform plan
   ```
3. Apply changes:
   ```bash
   terraform apply
   ```

## Disaster Recovery

### RTO/RPO Targets

- **RTO** (Recovery Time Objective): 30 minutes
- **RPO** (Recovery Point Objective): 5 minutes (PITR)

### DR Procedures

1. **Database Restore**:
   ```bash
   gcloud sql backups restore BACKUP_ID \
     --backup-instance=billing-platform-db-production
   ```

2. **Multi-Region Failover**:
   - Configure Cloud SQL cross-region replica
   - Use Cloud Load Balancer with multi-region backends
   - Automate failover with Cloud Functions

### DR Testing

Schedule regular DR tests:

```bash
# Create test instance from backup
gcloud sql instances clone billing-platform-db-production \
  billing-platform-db-dr-test
```

## Performance Optimization

### Cloud SQL

1. **Connection pooling** (via pgBouncer or Cloud SQL Proxy)
2. **Read replicas** for read-heavy workloads:
   ```bash
   gcloud sql instances create billing-platform-db-read-replica \
     --master-instance-name=billing-platform-db-production \
     --region=us-central1
   ```

### Cloud Run

1. **Increase max concurrency** for CPU-bound workloads
2. **Use Cloud CDN** for static assets
3. **Enable HTTP/2** (enabled by default)

### Memorystore Redis

1. **Use pipelining** for batch operations
2. **Monitor eviction metrics**:
   ```bash
   gcloud monitoring time-series list \
     --filter='metric.type="redis.googleapis.com/stats/evicted_keys"'
   ```

## Cleanup

To destroy all resources:

```bash
# Disable deletion protection
terraform apply -var="db_deletion_protection=false"

# Destroy infrastructure
terraform destroy
```

**Warning**: This will permanently delete all data. Ensure backups are created first.

## Support and Documentation

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud SQL Documentation](https://cloud.google.com/sql/docs)
- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [GCP Pricing Calculator](https://cloud.google.com/products/calculator)

## License

See main project LICENSE file.
