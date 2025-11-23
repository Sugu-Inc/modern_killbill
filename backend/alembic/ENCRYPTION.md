# Database Encryption at Rest - Implementation Guide

**Purpose**: SOC2 CC6.6 and GDPR Article 32 compliance
**Requirement**: Encrypt sensitive data at rest to protect against physical storage compromise
**Priority**: High Risk - Required for production deployment

---

## Overview

Encryption at rest protects data stored on disk from unauthorized access if physical storage is compromised (stolen drives, improper disposal, datacenter breach).

**Two approaches** are available:

1. **PostgreSQL Transparent Data Encryption (TDE)** - Application-transparent, database-level encryption
2. **Volume-Level Encryption** - OS/cloud provider encryption of entire storage volumes

---

## Option 1: PostgreSQL Transparent Data Encryption (TDE)

### Requirements
- PostgreSQL 15+ with TDE extension
- Note: Native TDE is available in PostgreSQL Enterprise or via extensions like `pgcrypto`

### Implementation Steps

#### 1. Enable pgcrypto Extension

```sql
-- Run as superuser
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

#### 2. Create Encrypted Columns for Sensitive Data

For highly sensitive fields (payment tokens, SSNs, etc.), use column-level encryption:

```sql
-- Example: Encrypt payment method details
ALTER TABLE payment_methods
  ADD COLUMN encrypted_data bytea;

-- Encrypt existing data
UPDATE payment_methods
  SET encrypted_data = pgp_sym_encrypt(
    card_last4::text,
    current_setting('app.encryption_key')
  );
```

#### 3. Application Configuration

Set encryption key in environment:

```bash
# .env
POSTGRES_ENCRYPTION_KEY="your-32-char-encryption-key-here"
```

Load in PostgreSQL:

```sql
-- Set session variable
SET app.encryption_key = 'your-32-char-encryption-key-here';
```

### Pros
- Fine-grained control over what's encrypted
- Can use different keys for different data types
- Works with standard PostgreSQL

### Cons
- Requires application changes
- Performance overhead for encryption/decryption
- Key management complexity

---

## Option 2: Volume-Level Encryption (Recommended)

### Cloud Providers

#### AWS RDS

Enable encryption when creating RDS instance:

```bash
aws rds create-db-instance \
  --db-instance-identifier billing-prod-db \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --master-username admin \
  --master-user-password <password> \
  --allocated-storage 100 \
  --storage-encrypted \
  --kms-key-id arn:aws:kms:us-east-1:123456789:key/abc123 \
  --backup-retention-period 7
```

**Features:**
- AES-256 encryption
- Automated key rotation via AWS KMS
- Zero performance impact
- Encrypts all data: database files, logs, backups, snapshots

**Cost**: No additional charge for encryption

#### Google Cloud SQL

Enable encryption (default for Cloud SQL):

```bash
gcloud sql instances create billing-prod-db \
  --database-version=POSTGRES_15 \
  --tier=db-custom-2-7680 \
  --region=us-central1 \
  --storage-type=SSD \
  --storage-size=100GB \
  --database-flags=cloudsql.enable_pgaudit=on \
  --backup-start-time=02:00
```

**Features:**
- Encryption enabled by default
- Google-managed encryption keys (CMEK available)
- AES-256 encryption

#### Azure Database for PostgreSQL

Enable encryption:

```bash
az postgres server create \
  --resource-group billing-rg \
  --name billing-prod-db \
  --location eastus \
  --admin-user dbadmin \
  --admin-password <password> \
  --sku-name GP_Gen5_2 \
  --storage-size 102400 \
  --backup-retention 7 \
  --geo-redundant-backup Enabled \
  --infrastructure-encryption Enabled
```

**Features:**
- TDE with service-managed keys
- Infrastructure encryption available
- Encrypts data, logs, and backups

### Self-Hosted / On-Premises

#### LUKS Encryption (Linux)

1. **Create Encrypted Volume:**

```bash
# Create encrypted partition
cryptsetup luksFormat /dev/sdb1

# Open encrypted partition
cryptsetup luksOpen /dev/sdb1 pgdata

# Format and mount
mkfs.ext4 /dev/mapper/pgdata
mount /dev/mapper/pgdata /var/lib/postgresql/15/main
```

2. **Auto-Mount on Boot:**

```bash
# /etc/crypttab
pgdata /dev/sdb1 /root/pgdata.key luks

# /etc/fstab
/dev/mapper/pgdata /var/lib/postgresql/15/main ext4 defaults 0 2
```

#### dm-crypt + LUKS

More advanced option with hardware acceleration:

```bash
# Enable encryption with hardware acceleration
cryptsetup luksFormat --cipher aes-xts-plain64 \
  --key-size 512 \
  --hash sha256 \
  /dev/sdb1

# Performance test
cryptsetup benchmark
```

### Kubernetes Persistent Volumes

#### AWS EKS with EBS Encryption

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: encrypted-gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
  kmsKeyId: "arn:aws:kms:us-east-1:123456789:key/abc123"
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

#### GKE with Encrypted Persistent Disks

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: standard-rwo  # Encrypted by default
```

### Docker Volumes

```bash
# Create encrypted volume using cryptsetup
docker volume create \
  --driver local \
  --opt type=none \
  --opt device=/dev/mapper/pgdata \
  --opt o=bind \
  postgres-data
```

---

## Verification & Testing

### 1. Verify Encryption is Enabled

#### AWS RDS

```bash
aws rds describe-db-instances \
  --db-instance-identifier billing-prod-db \
  --query 'DBInstances[0].StorageEncrypted'
# Should return: true
```

#### GCP Cloud SQL

```bash
gcloud sql instances describe billing-prod-db \
  --format="get(settings.dataDiskType, settings.dataDiskSizeGb)"
```

#### Self-Hosted

```bash
# Check if data directory is on encrypted volume
lsblk -o NAME,TYPE,SIZE,ENCRYPTED,MOUNTPOINT

# Verify encryption status
cryptsetup status pgdata
```

### 2. Performance Testing

```sql
-- Benchmark query performance
EXPLAIN ANALYZE SELECT * FROM invoices
  WHERE created_at > NOW() - INTERVAL '30 days';

-- Check for performance degradation
-- Encrypted storage should have <5% overhead
```

### 3. Backup Verification

```bash
# Verify backups are also encrypted
aws rds describe-db-snapshots \
  --db-instance-identifier billing-prod-db \
  --query 'DBSnapshots[*].[DBSnapshotIdentifier,Encrypted]'
```

---

## Key Management Best Practices

### 1. Key Rotation

**AWS KMS:**
```bash
# Enable automatic key rotation (yearly)
aws kms enable-key-rotation --key-id abc123
```

**Manual Rotation:**
- Generate new key
- Re-encrypt data with new key
- Securely destroy old key

### 2. Key Storage

**DO:**
- ✅ Store keys in KMS (AWS KMS, GCP KMS, Azure Key Vault)
- ✅ Use hardware security modules (HSM) for production
- ✅ Implement key versioning
- ✅ Separate encryption keys per environment (dev/staging/prod)

**DON'T:**
- ❌ Store keys in application code
- ❌ Commit keys to version control
- ❌ Store keys in environment variables on shared systems
- ❌ Use same key across environments

### 3. Access Control

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "rds.amazonaws.com"
      },
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "rds.us-east-1.amazonaws.com"
        }
      }
    }
  ]
}
```

---

## Compliance Verification

### SOC2 CC6.6 Checklist

- [ ] Data at rest is encrypted with industry-standard algorithm (AES-256)
- [ ] Encryption keys are managed securely (KMS/HSM)
- [ ] Key rotation policy is defined and implemented
- [ ] Backups are encrypted
- [ ] Access to encryption keys is logged and audited
- [ ] Encryption status is monitored and alerted

### GDPR Article 32 Checklist

- [ ] Personal data is encrypted at rest
- [ ] Encryption protects against unauthorized access
- [ ] Encryption keys are protected
- [ ] Ability to restore data from encrypted backups is tested
- [ ] Data breach risk is reduced through encryption

---

## Implementation Recommendation

**For Production:**

1. **Cloud-Hosted (Recommended)**: Use cloud provider volume encryption
   - AWS RDS with KMS encryption
   - GCP Cloud SQL (encrypted by default)
   - Azure Database for PostgreSQL with TDE

2. **Self-Hosted**: Use LUKS volume encryption
   - Full disk encryption with hardware acceleration
   - Automated key management
   - Regular backup verification

3. **Kubernetes**: Use encrypted persistent volumes
   - Cloud provider encryption (EBS, GCP PD)
   - Secrets management for keys

**Why Volume Encryption?**
- Zero application changes required
- No performance impact
- Encrypts everything: data, logs, backups
- Managed by infrastructure team
- Auditable and compliant

---

## Migration Path

If database is already running without encryption:

### AWS RDS

```bash
# Create encrypted snapshot
aws rds create-db-snapshot \
  --db-instance-identifier billing-prod-db \
  --db-snapshot-identifier pre-encryption-snapshot

# Copy snapshot with encryption
aws rds copy-db-snapshot \
  --source-db-snapshot-identifier pre-encryption-snapshot \
  --target-db-snapshot-identifier encrypted-snapshot \
  --kms-key-id arn:aws:kms:us-east-1:123456789:key/abc123

# Restore from encrypted snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier billing-prod-db-encrypted \
  --db-snapshot-identifier encrypted-snapshot

# Update DNS/connection string
# Verify and switch traffic
# Delete old unencrypted instance
```

### Self-Hosted

```bash
# 1. Create encrypted volume
cryptsetup luksFormat /dev/sdb1

# 2. Stop PostgreSQL
systemctl stop postgresql

# 3. Backup data
pg_dumpall > /backup/full_backup.sql

# 4. Mount encrypted volume
cryptsetup luksOpen /dev/sdb1 pgdata
mkfs.ext4 /dev/mapper/pgdata
mount /dev/mapper/pgdata /var/lib/postgresql/15/main

# 5. Restore data
psql -f /backup/full_backup.sql

# 6. Start PostgreSQL
systemctl start postgresql

# 7. Verify
psql -c "SELECT count(*) FROM accounts;"
```

---

## Monitoring & Alerting

### CloudWatch Alarms (AWS)

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name rds-encryption-disabled \
  --alarm-description "Alert if RDS encryption is disabled" \
  --metric-name StorageEncrypted \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 1 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 1
```

### PostgreSQL Logging

```ini
# postgresql.conf
log_statement = 'ddl'
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

---

## Support & Documentation

- PostgreSQL Encryption: https://www.postgresql.org/docs/15/encryption-options.html
- AWS RDS Encryption: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html
- GCP Cloud SQL Encryption: https://cloud.google.com/sql/docs/postgres/data-security
- Azure PostgreSQL Encryption: https://docs.microsoft.com/en-us/azure/postgresql/concepts-security

---

**Status**: ✅ Ready for Implementation
**Next Steps**: Choose encryption approach based on deployment environment
