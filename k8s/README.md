# Kubernetes Deployment for Billing API

This directory contains Kubernetes manifests for deploying the Modern Subscription Billing Platform.

## Prerequisites

- Kubernetes cluster (1.24+)
- kubectl configured to access the cluster
- NGINX Ingress Controller
- Prometheus Operator (for monitoring)
- cert-manager (optional, for TLS certificates)

## Architecture

The deployment includes:

- **Deployment**: 3 replicas with rolling updates
- **Service**: ClusterIP service for internal communication
- **Ingress**: NGINX ingress with TLS, rate limiting, and CORS
- **HorizontalPodAutoscaler**: Auto-scaling based on CPU/memory
- **PodDisruptionBudget**: Ensures minimum 2 pods during disruptions
- **ServiceMonitor**: Prometheus metrics scraping
- **PrometheusRule**: Alert rules for FR-153 to FR-156

## Quick Start

### 1. Update Configuration

Edit `configmap.yaml` to set your environment-specific values:

```yaml
# configmap.yaml
data:
  COMPANY_NAME: "Your Company Name"
  LOGO_URL: "https://your-cdn.example.com/logo.png"
  CORS_ORIGINS: "https://app.example.com,https://dashboard.example.com"
```

Edit `configmap.yaml` to update secrets (use Sealed Secrets or external secrets manager in production):

```yaml
# configmap.yaml (Secret section)
stringData:
  database-url: "postgresql+asyncpg://user:password@postgres:5432/billing"
  redis-url: "redis://redis:6379/0"
  stripe-secret-key: "sk_live_..."
  stripe-webhook-secret: "whsec_..."
  secret-key: "your-secure-random-key"
  jwt-secret-key: "your-jwt-secret-key"
```

### 2. Build and Push Docker Image

```bash
cd ../backend
docker build -t ghcr.io/yourorg/billing-api:latest .
docker push ghcr.io/yourorg/billing-api:latest
```

### 3. Deploy to Kubernetes

Using kubectl:

```bash
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
kubectl apply -f autoscaling.yaml
kubectl apply -f servicemonitor.yaml
```

Or using Kustomize:

```bash
kubectl apply -k .
```

### 4. Verify Deployment

```bash
# Check pods
kubectl get pods -n billing

# Check service
kubectl get svc -n billing

# Check ingress
kubectl get ingress -n billing

# View logs
kubectl logs -n billing -l app=billing-api --tail=100 -f

# Check health
kubectl exec -n billing deployment/billing-api -- curl http://localhost:8000/health
```

## Health Checks

The deployment includes three types of health checks:

### Liveness Probe (FR-145)
- **Endpoint**: `/health`
- **Interval**: 10s
- **Timeout**: 3s
- **Failure threshold**: 3
- Restarts pod if fails

### Readiness Probe (FR-146)
- **Endpoint**: `/health/ready`
- **Interval**: 5s
- **Timeout**: 3s
- **Failure threshold**: 3
- Removes pod from service if fails
- Checks database and Redis connectivity

### Startup Probe
- **Endpoint**: `/health`
- **Interval**: 5s
- **Timeout**: 3s
- **Failure threshold**: 30 (150s total)
- Allows longer startup time

## Monitoring & Alerting

### Prometheus Metrics (FR-147, FR-150, FR-151)

The deployment exposes metrics at `/metrics`:

- **Business metrics**: invoices, payments, MRR, subscriptions
- **Performance metrics**: request duration, DB queries, connection pool
- **HTTP metrics**: request count, latency by endpoint

### Prometheus Alerts (FR-153 to FR-156)

Alert rules are defined in `servicemonitor.yaml`:

- **FR-153**: Error rate >1% (5min window)
- **FR-154**: P95 latency >500ms (5min window)
- **FR-155**: Database connection failures or pool exhaustion
- **FR-156**: Payment gateway failure rate >5% (15min window)

Additional alerts:
- Pod availability <2
- Memory usage >90%
- CPU usage >90%

## Scaling

### Manual Scaling

```bash
kubectl scale deployment billing-api -n billing --replicas=5
```

### Auto-scaling

HPA is configured to scale between 3-10 replicas based on:
- CPU utilization target: 70%
- Memory utilization target: 80%

## Security

### Security Features

- **Non-root user**: Runs as user 1000
- **Read-only root filesystem**
- **Dropped capabilities**: All capabilities dropped
- **Security headers**: X-Frame-Options, X-Content-Type-Options, etc.
- **Network policies**: (Add network policy manifest if needed)
- **Secrets management**: Use Sealed Secrets or external secrets manager

### TLS/SSL

Configure TLS in `ingress.yaml`:

```yaml
tls:
- hosts:
  - api.billing.example.com
  secretName: billing-api-tls
```

Use cert-manager for automatic certificate management:

```bash
kubectl annotate ingress billing-api -n billing \
  cert-manager.io/cluster-issuer=letsencrypt-prod
```

## Troubleshooting

### Pods not starting

```bash
kubectl describe pod -n billing <pod-name>
kubectl logs -n billing <pod-name>
```

### Database connection issues

```bash
# Test database connectivity from pod
kubectl exec -n billing deployment/billing-api -- \
  python -c "import asyncpg; print('DB check')"
```

### Check configuration

```bash
kubectl get configmap billing-config -n billing -o yaml
kubectl get secret billing-secrets -n billing -o yaml
```

### View metrics

```bash
kubectl port-forward -n billing service/billing-api 8000:8000
curl http://localhost:8000/metrics
```

## Maintenance

### Database Migrations

Run Alembic migrations:

```bash
kubectl exec -n billing deployment/billing-api -- \
  alembic upgrade head
```

### Rolling Updates

Update image tag in `kustomization.yaml` and apply:

```bash
kubectl apply -k .
```

Monitor rollout:

```bash
kubectl rollout status deployment billing-api -n billing
```

### Rollback

```bash
kubectl rollout undo deployment billing-api -n billing
```

## Production Checklist

- [ ] Update all secrets in `configmap.yaml`
- [ ] Configure external PostgreSQL database
- [ ] Configure external Redis cache
- [ ] Set up TLS certificates
- [ ] Configure Prometheus alerting
- [ ] Set up log aggregation (ELK, Loki, etc.)
- [ ] Configure network policies
- [ ] Enable pod security policies/admission controllers
- [ ] Set up backup strategy
- [ ] Configure distributed tracing (Jaeger, Tempo)
- [ ] Test disaster recovery procedures
- [ ] Configure resource quotas and limits
- [ ] Set up CI/CD pipeline
- [ ] Enable audit logging
- [ ] Configure WAF rules (if using ModSecurity)

## Architecture Diagram

```
                    ┌─────────────────┐
                    │   Ingress       │
                    │   (NGINX)       │
                    │   TLS, CORS     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Service       │
                    │   (ClusterIP)   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼─────┐       ┌────▼─────┐       ┌────▼─────┐
    │  Pod 1   │       │  Pod 2   │       │  Pod 3   │
    │ billing  │       │ billing  │       │ billing  │
    │   -api   │       │   -api   │       │   -api   │
    └──────────┘       └──────────┘       └──────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
         ┌────▼─────┐                 ┌────▼─────┐
         │ Postgres │                 │  Redis   │
         │          │                 │          │
         └──────────┘                 └──────────┘
```

## Support

For issues or questions:
- Check logs: `kubectl logs -n billing -l app=billing-api`
- Check events: `kubectl get events -n billing --sort-by='.lastTimestamp'`
- Review metrics: Access Grafana dashboards
- Check alerts: Review Alertmanager
