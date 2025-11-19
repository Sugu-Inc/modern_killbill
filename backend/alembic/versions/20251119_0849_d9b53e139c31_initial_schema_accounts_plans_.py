"""Initial schema: accounts, plans, subscriptions, invoices, payments, usage, credits, webhooks, audit

Revision ID: d9b53e139c31
Revises: 
Create Date: 2025-11-19 08:49:17.627123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9b53e139c31'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables for the billing platform."""
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Create enums
    op.execute("CREATE TYPE accountstatus AS ENUM ('active', 'warning', 'blocked')")
    op.execute("CREATE TYPE planinterval AS ENUM ('month', 'year')")
    op.execute("CREATE TYPE usagetype AS ENUM ('tiered', 'volume', 'graduated')")
    op.execute("CREATE TYPE subscriptionstatus AS ENUM ('trialing', 'active', 'past_due', 'cancelled', 'paused')")
    op.execute("CREATE TYPE invoicestatus AS ENUM ('draft', 'open', 'paid', 'void', 'past_due')")
    op.execute("CREATE TYPE paymentstatus AS ENUM ('pending', 'succeeded', 'failed', 'cancelled')")
    op.execute("CREATE TYPE webhookstatus AS ENUM ('pending', 'processing', 'succeeded', 'failed')")

    # 1. Accounts table (no dependencies)
    op.create_table(
        'accounts',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('timezone', sa.String(), nullable=False, server_default='UTC'),
        sa.Column('tax_exempt', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tax_id', sa.String(), nullable=True),
        sa.Column('vat_id', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('active', 'warning', 'blocked', name='accountstatus'), nullable=False, server_default='active'),
        sa.Column('deleted_at', sa.String(), nullable=True),
        sa.Column('extra_metadata', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_accounts_email'), 'accounts', ['email'])

    # 2. Payment Methods table (depends on accounts)
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('stripe_payment_method_id', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('last4', sa.String(length=4), nullable=True),
        sa.Column('exp_month', sa.Integer(), nullable=True),
        sa.Column('exp_year', sa.Integer(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payment_methods_account_id'), 'payment_methods', ['account_id'])
    op.create_index(op.f('ix_payment_methods_stripe_payment_method_id'), 'payment_methods', ['stripe_payment_method_id'], unique=True)

    # 3. Plans table (no dependencies)
    op.create_table(
        'plans',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('interval', sa.Enum('month', 'year', name='planinterval'), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('trial_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('usage_type', sa.Enum('tiered', 'volume', 'graduated', name='usagetype'), nullable=True),
        sa.Column('tiers', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('extra_metadata', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_plans_active'), 'plans', ['active'])

    # 4. Subscriptions table (depends on accounts, plans)
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('plan_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.Enum('trialing', 'active', 'past_due', 'cancelled', 'paused', name='subscriptionstatus'), nullable=False, server_default='active'),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('current_period_start', sa.DateTime(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(), nullable=False),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('trial_end', sa.DateTime(), nullable=True),
        sa.Column('pause_resumes_at', sa.DateTime(), nullable=True),
        sa.Column('pending_plan_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
        sa.ForeignKeyConstraint(['pending_plan_id'], ['plans.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscriptions_account_id'), 'subscriptions', ['account_id'])
    op.create_index(op.f('ix_subscriptions_plan_id'), 'subscriptions', ['plan_id'])
    op.create_index(op.f('ix_subscriptions_status'), 'subscriptions', ['status'])
    op.create_index(op.f('ix_subscriptions_current_period_end'), 'subscriptions', ['current_period_end'])

    # 5. Subscription History table (depends on subscriptions)
    op.create_table(
        'subscription_history',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('subscription_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('old_value', sa.String(), nullable=True),
        sa.Column('new_value', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscription_history_subscription_id'), 'subscription_history', ['subscription_id'])

    # 6. Invoices table (depends on accounts, subscriptions)
    op.create_table(
        'invoices',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('subscription_id', sa.UUID(), nullable=True),
        sa.Column('number', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('draft', 'open', 'paid', 'void', 'past_due', name='invoicestatus'), nullable=False, server_default='draft'),
        sa.Column('amount_due', sa.Integer(), nullable=False),
        sa.Column('amount_paid', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tax', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('due_date', sa.DateTime(), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('voided_at', sa.DateTime(), nullable=True),
        sa.Column('line_items', sa.dialects.postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('extra_metadata', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoices_account_id'), 'invoices', ['account_id'])
    op.create_index(op.f('ix_invoices_subscription_id'), 'invoices', ['subscription_id'])
    op.create_index(op.f('ix_invoices_number'), 'invoices', ['number'], unique=True)
    op.create_index(op.f('ix_invoices_status'), 'invoices', ['status'])
    op.create_index(op.f('ix_invoices_due_date'), 'invoices', ['due_date'])

    # 7. Payments table (depends on invoices, payment_methods)
    op.create_table(
        'payments',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('status', sa.Enum('pending', 'succeeded', 'failed', 'cancelled', name='paymentstatus'), nullable=False, server_default='pending'),
        sa.Column('payment_gateway_transaction_id', sa.String(), nullable=True),
        sa.Column('payment_method_id', sa.UUID(), nullable=True),
        sa.Column('failure_message', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_method_id'], ['payment_methods.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payments_invoice_id'), 'payments', ['invoice_id'])
    op.create_index(op.f('ix_payments_status'), 'payments', ['status'])
    op.create_index(op.f('ix_payments_payment_gateway_transaction_id'), 'payments', ['payment_gateway_transaction_id'], unique=True)
    op.create_index(op.f('ix_payments_idempotency_key'), 'payments', ['idempotency_key'], unique=True)

    # 8. Usage Records table (depends on subscriptions)
    op.create_table(
        'usage_records',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('subscription_id', sa.UUID(), nullable=False),
        sa.Column('metric', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('extra_metadata', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_records_subscription_id'), 'usage_records', ['subscription_id'])
    op.create_index(op.f('ix_usage_records_metric'), 'usage_records', ['metric'])
    op.create_index(op.f('ix_usage_records_timestamp'), 'usage_records', ['timestamp'])
    op.create_index(op.f('ix_usage_records_idempotency_key'), 'usage_records', ['idempotency_key'], unique=True)

    # 9. Credits table (depends on accounts, invoices)
    op.create_table(
        'credits',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('applied_to_invoice_id', sa.UUID(), nullable=True),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['applied_to_invoice_id'], ['invoices.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_credits_account_id'), 'credits', ['account_id'])
    op.create_index(op.f('ix_credits_expires_at'), 'credits', ['expires_at'])

    # 10. Webhook Events table (no dependencies)
    op.create_table(
        'webhook_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('payload', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'processing', 'succeeded', 'failed', name='webhookstatus'), nullable=False, server_default='pending'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_webhook_events_event_type'), 'webhook_events', ['event_type'])
    op.create_index(op.f('ix_webhook_events_status'), 'webhook_events', ['status'])

    # 11. Audit Log table (no dependencies)
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('changes', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'])
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'])
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'])

    # 12. Analytics Snapshots table (no dependencies)
    op.create_table(
        'analytics_snapshots',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('metric_name', sa.String(), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('extra_metadata', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analytics_snapshots_metric_name'), 'analytics_snapshots', ['metric_name'])
    op.create_index(op.f('ix_analytics_snapshots_period'), 'analytics_snapshots', ['period'])


def downgrade() -> None:
    """Drop all tables."""
    # Drop tables in reverse dependency order
    op.drop_table('analytics_snapshots')
    op.drop_table('audit_logs')
    op.drop_table('webhook_events')
    op.drop_table('credits')
    op.drop_table('usage_records')
    op.drop_table('payments')
    op.drop_table('invoices')
    op.drop_table('subscription_history')
    op.drop_table('subscriptions')
    op.drop_table('plans')
    op.drop_table('payment_methods')
    op.drop_table('accounts')

    # Drop enums
    op.execute("DROP TYPE IF EXISTS webhookstatus")
    op.execute("DROP TYPE IF EXISTS paymentstatus")
    op.execute("DROP TYPE IF EXISTS invoicestatus")
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
    op.execute("DROP TYPE IF EXISTS usagetype")
    op.execute("DROP TYPE IF EXISTS planinterval")
    op.execute("DROP TYPE IF EXISTS accountstatus")
