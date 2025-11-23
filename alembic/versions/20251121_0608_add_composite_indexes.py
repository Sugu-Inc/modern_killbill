"""Add composite indexes for common query patterns

Revision ID: 20251121_0608
Revises: d9b53e139c31
Create Date: 2025-11-21 06:08:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251121_0608'
down_revision = 'd9b53e139c31'
branch_labels = None
depends_on = None


def upgrade():
    """Add composite indexes for common query patterns."""

    # Subscriptions: account_id + status (list active subscriptions per account)
    op.create_index(
        'ix_subscriptions_account_status',
        'subscriptions',
        ['account_id', 'status'],
        unique=False
    )

    # Subscriptions: status + current_period_end (find subscriptions to bill)
    op.create_index(
        'ix_subscriptions_status_period_end',
        'subscriptions',
        ['status', 'current_period_end'],
        unique=False
    )

    # Invoices: account_id + status (find unpaid invoices per account)
    op.create_index(
        'ix_invoices_account_status',
        'invoices',
        ['account_id', 'status'],
        unique=False
    )

    # Invoices: status + due_date (find overdue invoices)
    op.create_index(
        'ix_invoices_status_due_date',
        'invoices',
        ['status', 'due_date'],
        unique=False
    )

    # Payments: invoice_id + status (find payment status for invoices)
    op.create_index(
        'ix_payments_invoice_status',
        'payments',
        ['invoice_id', 'status'],
        unique=False
    )

    # Audit logs: entity_type + entity_id + created_at (search audit trail)
    op.create_index(
        'ix_audit_logs_entity_created',
        'audit_logs',
        ['entity_type', 'entity_id', 'created_at'],
        unique=False
    )

    # Usage records: subscription_id + timestamp (calculate usage for billing period)
    op.create_index(
        'ix_usage_records_subscription_timestamp',
        'usage_records',
        ['subscription_id', 'timestamp'],
        unique=False
    )

    # Credits: account_id + applied_to_invoice_id (find available credits)
    op.create_index(
        'ix_credits_account_applied',
        'credits',
        ['account_id', 'applied_to_invoice_id'],
        unique=False
    )


def downgrade():
    """Remove composite indexes."""

    op.drop_index('ix_credits_account_applied', table_name='credits')
    op.drop_index('ix_usage_records_subscription_timestamp', table_name='usage_records')
    op.drop_index('ix_audit_logs_entity_created', table_name='audit_logs')
    op.drop_index('ix_payments_invoice_status', table_name='payments')
    op.drop_index('ix_invoices_status_due_date', table_name='invoices')
    op.drop_index('ix_invoices_account_status', table_name='invoices')
    op.drop_index('ix_subscriptions_status_period_end', table_name='subscriptions')
    op.drop_index('ix_subscriptions_account_status', table_name='subscriptions')
