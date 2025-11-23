# Production Infrastructure - Modern Subscription Billing Platform

Infrastructure as Code (IaC) for deploying the Modern Subscription Billing Platform on AWS and GCP.

## Overview

This directory contains production-ready Terraform configurations for deploying the billing platform on major cloud providers:

- **AWS** - ECS Fargate, RDS PostgreSQL, ElastiCache Redis
- **GCP** - Cloud Run, Cloud SQL, Memorystore Redis

## Architecture Comparison

| Component | AWS | GCP |
|-----------|-----|-----|
| **Compute** | ECS Fargate | Cloud Run |
| **Database** | RDS PostgreSQL 15 | Cloud SQL PostgreSQL 15 |
| **Cache** | ElastiCache Redis 7 | Memorystore Redis 7 |
| **Load Balancer** | Application Load Balancer | Cloud Load Balancer |
| **Secrets** | Secrets Manager | Secret Manager |
| **Encryption** | KMS | Cloud KMS |
| **Monitoring** | CloudWatch | Cloud Monitoring |

## Quick Start

### AWS Deployment

```bash
cd aws
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your configuration
terraform init
terraform plan
terraform apply
```

See [aws/README.md](aws/README.md) for detailed instructions.

### GCP Deployment

```bash
cd gcp
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your configuration
terraform init
terraform plan
terraform apply
```

See [gcp/README.md](gcp/README.md) for detailed instructions.

## Features

### Security
- ✅ Encryption at rest with KMS/Cloud KMS
- ✅ Encryption in transit (TLS 1.3)
- ✅ Secrets management (Secrets Manager/Secret Manager)
- ✅ Least-privilege IAM/service accounts
- ✅ Network isolation with VPC
- ✅ Automated key rotation

### High Availability
- ✅ Multi-AZ/Regional deployments
- ✅ Auto-scaling (2-10 instances)
- ✅ Automated failover for databases
- ✅ Health checks and self-healing
- ✅ Load balancing with HTTPS termination

### Observability
- ✅ Centralized logging (CloudWatch/Cloud Logging)
- ✅ Metrics and dashboards
- ✅ Alerting for critical events
- ✅ Request tracing
- ✅ Performance insights

### Backup & Recovery
- ✅ Automated database backups (30-day retention)
- ✅ Point-in-time recovery
- ✅ Encrypted backups
- ✅ Cross-region replication (optional)

## Cost Estimates

### AWS (us-east-1)
- **Production**: ~$505/month
  - RDS PostgreSQL (db.t3.medium): $120
  - ElastiCache Redis (cache.t3.medium x2): $100
  - ECS Fargate (2-10 tasks, avg 4): $150
  - ALB + Data Transfer: $115
  - CloudWatch: $20

### GCP (us-central1)
- **Production**: ~$648/month
  - Cloud SQL (db-custom-2-7680, HA): $280
  - Memorystore Redis (4GB, HA): $200
  - Cloud Run (2 vCPU, 2GB RAM): $120
  - Load Balancer: $18
  - Logging + Monitoring: $30

**Note**: Costs can be reduced by 30-50% with:
- Reserved instances / Committed use discounts
- Spot/preemptible instances for dev/staging
- Right-sizing based on actual usage

## Deployment Checklist

### Pre-Deployment

- [ ] Choose cloud provider (AWS or GCP)
- [ ] Create cloud account with billing enabled
- [ ] Install Terraform 1.5+
- [ ] Configure cloud CLI (aws-cli or gcloud)
- [ ] Create container registry (ECR or Artifact Registry)
- [ ] Build and push Docker image
- [ ] Request SSL certificate (ACM or managed certificate)
- [ ] Configure DNS domain

### Deployment

- [ ] Copy and edit terraform.tfvars
- [ ] Set sensitive variables via environment variables
- [ ] Run `terraform init`
- [ ] Review `terraform plan` output
- [ ] Run `terraform apply`
- [ ] Update secrets in Secrets Manager
- [ ] Run database migrations
- [ ] Configure DNS to point to load balancer
- [ ] Wait for SSL certificate provisioning (AWS: manual, GCP: automatic)

### Post-Deployment

- [ ] Verify health endpoint responds
- [ ] Test API endpoints
- [ ] Review logs for errors
- [ ] Set up monitoring alerts
- [ ] Configure backup retention
- [ ] Document disaster recovery procedures
- [ ] Set up CI/CD pipeline
- [ ] Enable auto-scaling metrics

## Environment-Specific Configurations

### Production
- Multi-AZ/Regional HA deployments
- Automated backups with 30-day retention
- Deletion protection enabled
- Enhanced monitoring and alerting
- Min 2 instances with auto-scaling to 10

### Staging
- Single-AZ/Zonal deployments (cost savings)
- Automated backups with 7-day retention
- Deletion protection disabled
- Basic monitoring
- Min 1 instance with auto-scaling to 5

### Development
- Single-AZ/Zonal deployments
- Automated backups with 1-day retention
- Deletion protection disabled
- Minimal monitoring
- Min 0-1 instances with auto-scaling to 3

## Maintenance

### Regular Tasks

**Weekly:**
- Review CloudWatch/Cloud Monitoring metrics
- Check for security updates
- Review log aggregations for errors

**Monthly:**
- Review and optimize costs
- Test backup restoration procedures
- Update dependencies and container images
- Review and adjust auto-scaling thresholds

**Quarterly:**
- Conduct disaster recovery drills
- Review and update IAM permissions
- Audit security configurations
- Update SSL certificates if needed

### Updates

**Application Updates:**
```bash
# Build and push new image
docker build -t billing-platform:v1.1.0 .
docker push <registry>/billing-platform:v1.1.0

# AWS
aws ecs update-service --force-new-deployment ...

# GCP
gcloud run services update ... --image=...
```

**Infrastructure Updates:**
```bash
# Update terraform.tfvars or variables.tf
terraform plan
terraform apply
```

## Disaster Recovery

### Recovery Time Objectives (RTO)
- **AWS**: 1 hour
- **GCP**: 30 minutes

### Recovery Point Objectives (RPO)
- **AWS**: 5 minutes (automated backups + PITR)
- **GCP**: 5 minutes (automated backups + PITR)

### DR Procedures

1. **Database Restore**: Restore from latest automated backup
2. **Service Recovery**: ECS/Cloud Run auto-restart failed tasks
3. **Multi-Region Failover**: Manual DNS update or Route53/Cloud DNS health checks
4. **Complete Region Failure**: Restore in different region from backup

See provider-specific READMEs for detailed DR procedures.

## Monitoring and Alerts

### Critical Alerts (PagerDuty/On-Call)
- Database down
- Application instances all failing health checks
- Storage > 90% full
- 5xx error rate > 1% of requests

### Warning Alerts (Email/Slack)
- CPU > 80% for 5 minutes
- Memory > 80% for 5 minutes
- Response time P95 > 1 second
- Failed health checks
- Backup failures

### Info Notifications
- Successful deployments
- Auto-scaling events
- Scheduled maintenance windows

## Security Compliance

### SOC2 Controls
- ✅ CC6.6: Encryption at rest and in transit
- ✅ CC6.7: Secrets management
- ✅ CC7.2: Security monitoring and logging
- ✅ CC7.3: Incident response procedures
- ✅ CC8.1: Change management (Infrastructure as Code)

### GDPR Requirements
- ✅ Article 32: Data encryption
- ✅ Article 33: Security incident detection (monitoring)
- ✅ Article 32: Pseudonymization capability
- ✅ Data retention and deletion procedures

## Multi-Cloud Strategy

### Why Support Both AWS and GCP?

1. **Avoid Vendor Lock-in**: Flexibility to switch or use both
2. **Regional Coverage**: Better global latency with multi-cloud
3. **Cost Optimization**: Compare pricing and use cheaper provider
4. **Disaster Recovery**: Cross-cloud failover capability
5. **Customer Requirements**: Some customers require specific clouds

### Migration Between Clouds

```bash
# Export data from current cloud
pg_dump > backup.sql
redis-cli --rdb dump.rdb

# Deploy to new cloud
cd <new-cloud-provider>
terraform apply

# Import data
psql < backup.sql
redis-cli --pipe < dump.rdb

# Update DNS to new load balancer
```

## Troubleshooting

### Common Issues

**Terraform State Lock:**
```bash
# AWS
aws dynamodb delete-item --table-name terraform-state-lock --key '{"LockID":{"S":"..."}}'

# GCP
gsutil rm gs://billing-platform-terraform-state/production/state/default.tflock
```

**DNS Not Resolving:**
- Verify DNS propagation (can take up to 48 hours)
- Check load balancer is healthy
- Verify SSL certificate is active

**Database Connection Failures:**
- Check security group/firewall rules
- Verify VPC/network configuration
- Test with Cloud SQL Proxy / bastion host

## Best Practices

### Infrastructure as Code
- ✅ All infrastructure defined in Terraform
- ✅ State stored remotely with locking
- ✅ Separate environments (prod/staging/dev)
- ✅ Use modules for reusable components
- ✅ Pin provider versions

### Security
- ✅ Never commit secrets to version control
- ✅ Use environment variables for sensitive data
- ✅ Enable encryption everywhere
- ✅ Principle of least privilege
- ✅ Regular security audits

### Operations
- ✅ Automated backups and tested restores
- ✅ Monitoring and alerting configured
- ✅ Runbooks for common incidents
- ✅ Regular disaster recovery drills
- ✅ Capacity planning reviews

## Support

For issues or questions:

1. Check provider-specific README:
   - [AWS Documentation](aws/README.md)
   - [GCP Documentation](gcp/README.md)

2. Review Terraform documentation:
   - [AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
   - [GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)

3. Check cloud provider documentation:
   - [AWS Documentation](https://docs.aws.amazon.com/)
   - [GCP Documentation](https://cloud.google.com/docs)

## License

See main project LICENSE file.
