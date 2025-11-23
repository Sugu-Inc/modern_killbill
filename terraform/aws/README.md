# AWS Infrastructure - Modern Subscription Billing Platform

Production-ready Terraform configuration for deploying the Modern Subscription Billing Platform on AWS.

## Architecture Overview

```
Internet
    |
    v
Application Load Balancer (HTTPS)
    |
    v
ECS Fargate Cluster (Private Subnets)
    |
    +-- API Service (Auto-scaling 2-10 instances)
    |
    +-- Background Workers
    |
    v
RDS PostgreSQL 15 (Multi-AZ, Encrypted)
    |
    v
ElastiCache Redis 7 (Multi-AZ, Encrypted)
```

## Infrastructure Components

### Networking
- **VPC** with public and private subnets across 2 availability zones
- **Internet Gateway** for public internet access
- **NAT Gateway** for private subnet internet access
- **Security Groups** for ALB, ECS, RDS, and Redis

### Compute
- **ECS Fargate** cluster with auto-scaling (2-10 tasks)
- **Application Load Balancer** with HTTPS termination
- CPU-based and memory-based auto-scaling policies

### Data Storage
- **RDS PostgreSQL 15** with:
  - Multi-AZ deployment
  - Automated backups (30-day retention)
  - Encryption at rest with KMS
  - Performance Insights enabled
- **ElastiCache Redis 7** with:
  - Multi-node replication
  - Encryption at rest and in transit
  - Automated failover

### Security
- **KMS** encryption keys with automatic rotation
- **AWS Secrets Manager** for sensitive data (DB password, Stripe API key, JWT secret)
- **Security Groups** with least-privilege access
- **IAM Roles** for ECS tasks with minimal permissions

### Monitoring
- **CloudWatch Log Groups** for application and worker logs
- **CloudWatch Alarms** for:
  - ALB response time
  - 5xx errors
  - RDS CPU and storage
  - Redis CPU utilization
- **Container Insights** for ECS metrics

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
   ```bash
   aws configure
   ```

2. **Terraform** 1.5 or later
   ```bash
   terraform version
   ```

3. **ACM Certificate** for HTTPS (must be created beforehand)
   ```bash
   aws acm request-certificate \
     --domain-name billing.example.com \
     --validation-method DNS
   ```

4. **ECR Repository** for Docker images
   ```bash
   aws ecr create-repository --repository-name billing-platform
   ```

5. **S3 Bucket** for Terraform state (create manually or comment out backend in main.tf)
   ```bash
   aws s3api create-bucket \
     --bucket billing-platform-terraform-state \
     --region us-east-1

   aws s3api put-bucket-versioning \
     --bucket billing-platform-terraform-state \
     --versioning-configuration Status=Enabled

   aws dynamodb create-table \
     --table-name terraform-state-lock \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST
   ```

## Deployment Steps

### 1. Configure Variables

Copy the example variables file and customize:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set:
- `db_password` - Strong database password
- `ecr_repository_url` - Your ECR repository URL
- `acm_certificate_arn` - Your ACM certificate ARN
- Other environment-specific values

**Security Note**: Never commit `terraform.tfvars` to version control. Set sensitive values via environment variables:

```bash
export TF_VAR_db_password="your-strong-password"
```

### 2. Build and Push Docker Image

```bash
# Build the Docker image
cd ../../backend
docker build -t billing-platform:v1.0.0 .

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag billing-platform:v1.0.0 \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/billing-platform:v1.0.0

docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/billing-platform:v1.0.0
```

### 3. Initialize Terraform

```bash
cd terraform/aws
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

**Deployment time**: Approximately 15-20 minutes.

### 6. Store Secrets in AWS Secrets Manager

After infrastructure is created, update secrets:

```bash
# Update Stripe API key
aws secretsmanager put-secret-value \
  --secret-id billing-platform-stripe-api-key-production \
  --secret-string "sk_live_your_stripe_key"

# Update JWT secret
aws secretsmanager put-secret-value \
  --secret-id billing-platform-jwt-secret-production \
  --secret-string "your-jwt-secret-key"
```

### 7. Run Database Migrations

Connect to RDS and run Alembic migrations:

```bash
# Get RDS endpoint from Terraform outputs
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)

# Run migrations (from a bastion host or via ECS task)
alembic upgrade head
```

### 8. Verify Deployment

Get the ALB DNS name:

```bash
terraform output alb_dns_name
```

Test the API:

```bash
curl https://<alb-dns-name>/health
```

## Terraform Outputs

After deployment, useful outputs:

```bash
# Get all outputs
terraform output

# Specific outputs
terraform output vpc_id
terraform output rds_endpoint
terraform output redis_endpoint
terraform output alb_dns_name
terraform output ecs_cluster_name
```

## DNS Configuration

Update your DNS to point to the ALB:

```bash
# Get ALB DNS name
ALB_DNS=$(terraform output -raw alb_dns_name)

# Create CNAME record
# billing.example.com -> <ALB_DNS>
```

## Scaling

### Manual Scaling

Adjust desired task count:

```bash
aws ecs update-service \
  --cluster billing-platform-cluster-production \
  --service billing-platform-app-service-production \
  --desired-count 5
```

### Auto-Scaling

Auto-scaling is configured by default:
- **CPU Target**: 70% average utilization
- **Memory Target**: 80% average utilization
- **Min**: 2 tasks
- **Max**: 10 tasks

Adjust in `variables.tf`:
```hcl
variable "app_min_count" {
  default = 2
}

variable "app_max_count" {
  default = 10
}
```

## Monitoring and Logging

### CloudWatch Logs

View application logs:

```bash
aws logs tail /ecs/billing-platform-app-production --follow
```

### CloudWatch Alarms

View active alarms:

```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix billing-platform
```

### ECS Container Insights

View metrics in AWS Console:
- ECS → Clusters → billing-platform-cluster-production → Metrics

## Backup and Recovery

### RDS Backups

- **Automated backups**: 30-day retention (configurable)
- **Backup window**: 03:00-04:00 UTC
- **Maintenance window**: Monday 04:00-05:00 UTC

Create manual snapshot:

```bash
aws rds create-db-snapshot \
  --db-instance-identifier billing-platform-db-production \
  --db-snapshot-identifier manual-snapshot-$(date +%Y%m%d)
```

Restore from snapshot:

```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier billing-platform-db-restored \
  --db-snapshot-identifier manual-snapshot-20251121
```

### Redis Backups

- **Automated snapshots**: 7-day retention
- **Snapshot window**: 03:00-05:00 UTC

## Cost Optimization

### Production Cost Estimate (us-east-1)

| Resource | Configuration | Monthly Cost (approx) |
|----------|--------------|----------------------|
| RDS PostgreSQL | db.t3.medium, 100GB | $120 |
| ElastiCache Redis | cache.t3.medium x2 | $100 |
| ECS Fargate | 2-10 tasks (avg 4) | $150 |
| ALB | Standard | $25 |
| Data Transfer | 1TB | $90 |
| CloudWatch | Logs + Alarms | $20 |
| **Total** | | **~$505/month** |

### Cost Reduction Strategies

1. **Use Savings Plans** for predictable workloads
2. **Enable RDS auto-scaling storage** (already configured)
3. **Use FARGATE_SPOT** for non-critical tasks
4. **Optimize log retention** (reduce to 7 days for dev/staging)
5. **Schedule downtime** for dev/staging environments

```bash
# Example: Stop RDS during off-hours
aws rds stop-db-instance --db-instance-identifier billing-platform-db-staging
```

## Security Best Practices

### Implemented

✅ Encryption at rest (RDS, Redis, Secrets Manager, CloudWatch Logs)
✅ Encryption in transit (TLS 1.3 on ALB, Redis)
✅ Least-privilege IAM roles
✅ Security groups with minimal access
✅ KMS key rotation enabled
✅ Multi-AZ deployments
✅ Automated backups
✅ Container Insights enabled

### Additional Recommendations

- [ ] Enable AWS GuardDuty for threat detection
- [ ] Configure AWS Config for compliance monitoring
- [ ] Enable VPC Flow Logs
- [ ] Set up AWS WAF for ALB
- [ ] Configure CloudTrail for audit logging
- [ ] Implement secrets rotation with Lambda

## Troubleshooting

### Common Issues

#### 1. ECS Tasks Not Starting

Check task logs:
```bash
aws logs tail /ecs/billing-platform-app-production --follow
```

Common causes:
- Invalid environment variables
- Cannot pull Docker image from ECR
- Health check failures

#### 2. Database Connection Errors

Verify security group rules:
```bash
aws ec2 describe-security-groups \
  --group-ids <rds-security-group-id>
```

#### 3. 502 Bad Gateway from ALB

Check:
- ECS tasks are running
- Health check endpoint returns 200
- Security group allows ALB → ECS traffic

#### 4. High RDS CPU

Enable Performance Insights:
```bash
aws rds modify-db-instance \
  --db-instance-identifier billing-platform-db-production \
  --enable-performance-insights
```

## Updating Infrastructure

### Update Application Version

1. Build and push new Docker image
2. Update task definition:

```bash
# Update variables
export NEW_VERSION="v1.1.0"

# Update terraform.tfvars
sed -i 's/app_image_tag = .*/app_image_tag = "'$NEW_VERSION'"/' terraform.tfvars

# Apply changes
terraform apply
```

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

### Zero-Downtime Deployments

ECS handles rolling deployments automatically:
- New tasks are started
- Health checks pass
- Old tasks are drained and stopped

## Disaster Recovery

### RTO/RPO Targets

- **RTO** (Recovery Time Objective): 1 hour
- **RPO** (Recovery Point Objective): 5 minutes (automated backups)

### DR Procedures

1. **Database Restore**:
   ```bash
   # Restore from automated backup
   aws rds restore-db-instance-to-point-in-time \
     --source-db-instance-identifier billing-platform-db-production \
     --target-db-instance-identifier billing-platform-db-restored \
     --restore-time 2025-11-21T12:00:00Z
   ```

2. **Multi-Region Failover**:
   - Set up read replicas in another region
   - Configure Route53 health checks
   - Automate failover with Lambda

## Cleanup

To destroy all resources:

```bash
# Disable deletion protection
terraform apply -var="alb_deletion_protection=false"

# Destroy infrastructure
terraform destroy
```

**Warning**: This will permanently delete all data. Ensure backups are created first.

## Support and Documentation

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [AWS RDS Documentation](https://docs.aws.amazon.com/rds/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

## License

See main project LICENSE file.
