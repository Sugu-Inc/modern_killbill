"""create analytics_snapshots table

Revision ID: 20251121_analytics
Revises: 20251121_encrypt
Create Date: 2025-11-21 08:00:00

Create analytics_snapshots table for pre-calculated SaaS metrics.
Supports FR-117 to FR-121 (Analytics & Reporting requirements).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20251121_analytics'
down_revision = '20251121_encrypt'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create analytics_snapshots table."""
    op.create_table(
        'analytics_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            'metric_name',
            sa.String(length=100),
            nullable=False,
            comment='Metric name: mrr, churn_rate, ltv, usage_trend'
        ),
        sa.Column(
            'value',
            sa.Numeric(precision=15, scale=2),
            nullable=False,
            comment='Metric value (e.g., $12,345.67 for MRR)'
        ),
        sa.Column(
            'period',
            sa.Date(),
            nullable=False,
            comment='Date for this metric snapshot'
        ),
        sa.Column(
            'metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Additional metric details (breakdown by plan, segment, etc.)'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
            comment='Snapshot calculation timestamp'
        ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index(
        'ix_analytics_snapshots_metric_name',
        'analytics_snapshots',
        ['metric_name']
    )

    op.create_index(
        'ix_analytics_snapshots_period',
        'analytics_snapshots',
        ['period']
    )

    # Create unique composite index (one snapshot per metric per period)
    op.create_index(
        'ix_analytics_snapshots_metric_period',
        'analytics_snapshots',
        ['metric_name', 'period'],
        unique=True
    )


def downgrade() -> None:
    """Drop analytics_snapshots table."""
    op.drop_index('ix_analytics_snapshots_metric_period', table_name='analytics_snapshots')
    op.drop_index('ix_analytics_snapshots_period', table_name='analytics_snapshots')
    op.drop_index('ix_analytics_snapshots_metric_name', table_name='analytics_snapshots')
    op.drop_table('analytics_snapshots')
