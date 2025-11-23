"""encryption_at_rest_verification

Revision ID: 20251121_encrypt
Revises: 20251119_0849_d9b53e139c31
Create Date: 2025-11-21 07:00:00

This migration documents the requirement for database encryption at rest
and adds verification checks for SOC2 CC6.6 and GDPR Article 32 compliance.

**IMPORTANT**: This migration does NOT enable encryption itself.
Encryption must be configured at the infrastructure level.
See: backend/alembic/ENCRYPTION.md for implementation guide.

Verification checks:
1. Cloud deployments: Volume-level encryption via cloud provider (recommended)
2. Self-hosted: LUKS/dm-crypt volume encryption
3. Application-level: pgcrypto for sensitive column encryption (optional)

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '20251121_encrypt'
down_revision = '20251119_0849_d9b53e139c31'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Verify encryption at rest is configured.

    This migration adds comments to critical tables documenting the
    encryption requirement and optionally verifies encryption status.
    """
    connection = op.get_bind()

    # Add table comments documenting encryption requirement
    critical_tables = [
        ('accounts', 'Contains PII - requires encryption at rest'),
        ('payment_methods', 'Contains payment data - requires encryption at rest'),
        ('invoices', 'Contains financial data - requires encryption at rest'),
        ('payments', 'Contains transaction data - requires encryption at rest'),
        ('audit_logs', 'Contains audit trail - requires encryption at rest'),
        ('subscriptions', 'Contains business data - requires encryption at rest'),
    ]

    for table_name, comment in critical_tables:
        connection.execute(
            text(f"COMMENT ON TABLE {table_name} IS :comment"),
            {"comment": comment}
        )

    # Create a metadata table to track encryption verification
    op.create_table(
        'encryption_metadata',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('encryption_verified', sa.Boolean(), default=False),
        sa.Column('encryption_method', sa.String(100), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verified_by', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Add comment to metadata table
    connection.execute(
        text(
            "COMMENT ON TABLE encryption_metadata IS "
            "'Tracks encryption at rest verification for compliance audits'"
        )
    )

    # Insert initial record (encryption not yet verified)
    connection.execute(
        text(
            """
            INSERT INTO encryption_metadata
            (encryption_verified, encryption_method, notes)
            VALUES
            (false, 'PENDING', 'Encryption at rest must be configured at infrastructure level. See backend/alembic/ENCRYPTION.md for implementation guide.')
            """
        )
    )

    # Optional: Check if running on cloud provider with automatic encryption
    try:
        # AWS RDS detection
        result = connection.execute(
            text("SELECT version()")
        ).fetchone()

        version_string = result[0] if result else ""

        if "rds" in version_string.lower():
            connection.execute(
                text(
                    """
                    UPDATE encryption_metadata
                    SET notes = 'Running on AWS RDS. Verify encryption via: aws rds describe-db-instances --query DBInstances[*].[DBInstanceIdentifier,StorageEncrypted]'
                    WHERE id = 1
                    """
                )
            )

        elif "cloudsql" in version_string.lower():
            connection.execute(
                text(
                    """
                    UPDATE encryption_metadata
                    SET notes = 'Running on GCP Cloud SQL. Encryption is enabled by default. Verify via: gcloud sql instances describe INSTANCE_NAME'
                    WHERE id = 1
                    """
                )
            )

    except Exception as e:
        # Ignore if we can't detect cloud provider
        print(f"Could not detect cloud provider: {e}")

    print("\n" + "="*80)
    print("⚠️  ENCRYPTION AT REST VERIFICATION REQUIRED")
    print("="*80)
    print("\nThis migration documents the requirement for encryption at rest.")
    print("\n📋 Next Steps:")
    print("  1. Review implementation guide: backend/alembic/ENCRYPTION.md")
    print("  2. Configure encryption based on deployment environment:")
    print("     - AWS RDS: Enable storage encryption with KMS")
    print("     - GCP Cloud SQL: Encryption enabled by default")
    print("     - Azure: Enable TDE/infrastructure encryption")
    print("     - Self-hosted: Configure LUKS volume encryption")
    print("  3. Update encryption_metadata table after verification:")
    print("     UPDATE encryption_metadata SET")
    print("       encryption_verified = true,")
    print("       encryption_method = 'AWS-KMS' (or appropriate method),")
    print("       verified_at = CURRENT_TIMESTAMP,")
    print("       verified_by = 'your-name';")
    print("\n📚 Documentation: backend/alembic/ENCRYPTION.md")
    print("="*80 + "\n")


def downgrade() -> None:
    """
    Remove encryption verification metadata.
    """
    connection = op.get_bind()

    # Remove table comments
    critical_tables = [
        'accounts', 'payment_methods', 'invoices',
        'payments', 'audit_logs', 'subscriptions'
    ]

    for table_name in critical_tables:
        connection.execute(
            text(f"COMMENT ON TABLE {table_name} IS NULL")
        )

    # Drop metadata table
    op.drop_table('encryption_metadata')
