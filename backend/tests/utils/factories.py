"""Test data factories using Faker for generating realistic test data."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from faker import Faker

fake = Faker()


class AccountFactory:
    """Factory for creating test account data."""

    @staticmethod
    def create(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Create account test data.

        Args:
            overrides: Optional field overrides

        Returns:
            dict: Account data
        """
        data = {
            "id": uuid4(),
            "email": fake.email(),
            "name": fake.company(),
            "currency": fake.random_element(["USD", "EUR", "GBP"]),
            "timezone": fake.timezone(),
            "tax_exempt": fake.boolean(chance_of_getting_true=10),
            "metadata": {"source": "test"},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if overrides:
            data.update(overrides)
        return data


class PlanFactory:
    """Factory for creating test plan data."""

    @staticmethod
    def create(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Create plan test data.

        Args:
            overrides: Optional field overrides

        Returns:
            dict: Plan data
        """
        data = {
            "id": uuid4(),
            "name": f"{fake.word().title()} Plan",
            "interval": fake.random_element(["month", "year"]),
            "amount": fake.random_int(min=100, max=10000),
            "currency": "USD",
            "trial_days": fake.random_element([0, 7, 14, 30]),
            "usage_type": None,
            "tiers": None,
            "active": True,
            "version": 1,
            "created_at": datetime.utcnow(),
        }
        if overrides:
            data.update(overrides)
        return data


class SubscriptionFactory:
    """Factory for creating test subscription data."""

    @staticmethod
    def create(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Create subscription test data.

        Args:
            overrides: Optional field overrides

        Returns:
            dict: Subscription data
        """
        start_date = datetime.utcnow()
        data = {
            "id": uuid4(),
            "account_id": uuid4(),
            "plan_id": uuid4(),
            "status": "active",
            "quantity": 1,
            "current_period_start": start_date,
            "current_period_end": start_date + timedelta(days=30),
            "cancel_at_period_end": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if overrides:
            data.update(overrides)
        return data


class InvoiceFactory:
    """Factory for creating test invoice data."""

    @staticmethod
    def create(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Create invoice test data.

        Args:
            overrides: Optional field overrides

        Returns:
            dict: Invoice data
        """
        amount = fake.random_int(min=100, max=10000)
        data = {
            "id": uuid4(),
            "account_id": uuid4(),
            "subscription_id": uuid4(),
            "number": f"INV-{fake.random_int(min=1000, max=9999)}",
            "status": "draft",
            "amount_due": amount,
            "amount_paid": 0,
            "tax": int(amount * Decimal("0.1")),  # 10% tax
            "currency": "USD",
            "due_date": datetime.utcnow() + timedelta(days=7),
            "paid_at": None,
            "line_items": [
                {
                    "description": "Subscription charge",
                    "amount": amount,
                    "quantity": 1,
                }
            ],
            "metadata": {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if overrides:
            data.update(overrides)
        return data


class PaymentFactory:
    """Factory for creating test payment data."""

    @staticmethod
    def create(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Create payment test data.

        Args:
            overrides: Optional field overrides

        Returns:
            dict: Payment data
        """
        data = {
            "id": uuid4(),
            "invoice_id": uuid4(),
            "amount": fake.random_int(min=100, max=10000),
            "currency": "USD",
            "status": "pending",
            "payment_gateway_transaction_id": f"pi_{fake.random_letters(length=24)}",
            "payment_method_id": uuid4(),
            "failure_message": None,
            "idempotency_key": str(uuid4()),
            "created_at": datetime.utcnow(),
        }
        if overrides:
            data.update(overrides)
        return data


class UsageRecordFactory:
    """Factory for creating test usage record data."""

    @staticmethod
    def create(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Create usage record test data.

        Args:
            overrides: Optional field overrides

        Returns:
            dict: Usage record data
        """
        data = {
            "id": uuid4(),
            "subscription_id": uuid4(),
            "metric": fake.random_element(["api_calls", "storage_gb", "bandwidth_gb"]),
            "quantity": fake.random_int(min=1, max=1000),
            "timestamp": datetime.utcnow(),
            "idempotency_key": str(uuid4()),
            "metadata": {},
            "created_at": datetime.utcnow(),
        }
        if overrides:
            data.update(overrides)
        return data


class CreditFactory:
    """Factory for creating test credit data."""

    @staticmethod
    def create(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Create credit test data.

        Args:
            overrides: Optional field overrides

        Returns:
            dict: Credit data
        """
        data = {
            "id": uuid4(),
            "account_id": uuid4(),
            "amount": fake.random_int(min=100, max=5000),
            "currency": "USD",
            "reason": fake.sentence(),
            "applied_to_invoice_id": None,
            "created_at": datetime.utcnow(),
        }
        if overrides:
            data.update(overrides)
        return data
