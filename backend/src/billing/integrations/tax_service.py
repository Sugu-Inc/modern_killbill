"""Tax calculation service integration.

Integrates with Stripe Tax API for automatic tax calculation based on customer location.
"""
from decimal import Decimal
from typing import Any

import structlog
import stripe

from billing.config import settings
from billing.models.account import Account

logger = structlog.get_logger(__name__)


class TaxService:
    """
    Service for tax calculation using Stripe Tax API.

    Handles:
    - Tax calculation based on customer location
    - VAT ID validation (EU reverse charge)
    - Tax exemption handling
    - Tax rate caching
    """

    def __init__(self):
        """Initialize tax service with Stripe API key."""
        stripe.api_key = settings.stripe_secret_key

    async def calculate_tax_for_invoice(
        self,
        account: Account,
        amount: int,
        currency: str = "USD",
        line_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Calculate tax for an invoice using Stripe Tax.

        Args:
            account: Account to calculate tax for
            amount: Subtotal amount in cents
            currency: ISO 4217 currency code
            line_items: Optional line items for detailed tax calculation

        Returns:
            Dict with 'amount' (tax in cents), 'rate' (decimal), 'breakdown' (details)
        """
        try:
            # Check if account is tax exempt
            if account.tax_exempt:
                logger.info(
                    "account_tax_exempt",
                    account_id=str(account.id),
                    amount=amount,
                )
                return {
                    "amount": 0,
                    "rate": Decimal("0"),
                    "breakdown": [],
                    "reason": "tax_exempt",
                }

            # Validate VAT ID for EU reverse charge
            if account.vat_id:
                is_valid = await self.validate_vat_id(account.vat_id)
                if is_valid:
                    logger.info(
                        "vat_reverse_charge_applied",
                        account_id=str(account.id),
                        vat_id=account.vat_id,
                        amount=amount,
                    )
                    return {
                        "amount": 0,
                        "rate": Decimal("0"),
                        "breakdown": [],
                        "reason": "reverse_charge",
                        "vat_id": account.vat_id,
                    }

            # Calculate tax using Stripe Tax API
            tax_calculation = await self._calculate_with_stripe(
                account=account,
                amount=amount,
                currency=currency,
                line_items=line_items,
            )

            return tax_calculation

        except stripe.error.StripeError as e:
            logger.error(
                "stripe_tax_calculation_error",
                account_id=str(account.id),
                amount=amount,
                error=str(e),
            )
            # Fallback to simple tax calculation
            return await self._calculate_simple_tax(account, amount)
        except Exception as e:
            logger.exception(
                "tax_calculation_error",
                account_id=str(account.id),
                amount=amount,
                exc_info=e,
            )
            # Fallback to simple tax calculation
            return await self._calculate_simple_tax(account, amount)

    async def validate_vat_id(self, vat_id: str) -> bool:
        """
        Validate VAT ID using Stripe Tax validation.

        Args:
            vat_id: VAT identification number

        Returns:
            True if valid, False otherwise
        """
        try:
            # Use Stripe Tax validation API
            # Note: This requires Stripe Tax enabled on the account
            response = stripe.tax.Calculation.create(
                currency="eur",
                line_items=[
                    {
                        "amount": 1000,
                        "reference": "vat_validation",
                    }
                ],
                customer_details={
                    "address": {
                        "country": vat_id[:2],  # Extract country code from VAT ID
                    },
                    "tax_ids": [
                        {
                            "type": "eu_vat",
                            "value": vat_id,
                        }
                    ],
                },
            )

            # Check if reverse charge was applied (indicates valid VAT ID)
            is_valid = response.get("tax_breakdown", [{}])[0].get("tax_rate_details", {}).get("tax_type") == "reverse_charge"

            logger.info(
                "vat_validation_result",
                vat_id=vat_id,
                is_valid=is_valid,
            )

            return is_valid

        except stripe.error.StripeError as e:
            logger.warning(
                "vat_validation_failed",
                vat_id=vat_id,
                error=str(e),
            )
            return False

    async def get_current_tax_rate(
        self,
        country_code: str,
        state: str | None = None,
        postal_code: str | None = None,
    ) -> Decimal:
        """
        Get current tax rate for a location.

        Args:
            country_code: ISO 3166-1 alpha-2 country code
            state: State/province code (for US/Canada)
            postal_code: Postal/ZIP code

        Returns:
            Tax rate as decimal (e.g., 0.10 for 10%)
        """
        try:
            # Use Stripe Tax to get rate
            response = stripe.tax.Calculation.create(
                currency="usd",
                line_items=[
                    {
                        "amount": 1000,
                        "reference": "rate_lookup",
                    }
                ],
                customer_details={
                    "address": {
                        "country": country_code,
                        "state": state,
                        "postal_code": postal_code,
                    },
                },
            )

            # Extract tax rate
            tax_amount = response.get("tax_amount_exclusive", 0)
            subtotal = 1000
            tax_rate = Decimal(str(tax_amount)) / Decimal(str(subtotal))

            logger.info(
                "tax_rate_lookup",
                country=country_code,
                state=state,
                postal_code=postal_code,
                rate=float(tax_rate),
            )

            return tax_rate

        except stripe.error.StripeError as e:
            logger.error(
                "tax_rate_lookup_error",
                country=country_code,
                error=str(e),
            )
            # Return default rate
            return Decimal("0.10")

    async def _calculate_with_stripe(
        self,
        account: Account,
        amount: int,
        currency: str,
        line_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Calculate tax using Stripe Tax API.

        Args:
            account: Account to calculate tax for
            amount: Amount in cents
            currency: Currency code
            line_items: Line items for calculation

        Returns:
            Tax calculation result
        """
        # Prepare line items
        if not line_items:
            line_items = [
                {
                    "amount": amount,
                    "reference": "subscription",
                }
            ]

        # Extract country from timezone or use default
        # TODO: Enhance with actual address data when available
        country_code = "US"  # Default to US
        if account.timezone:
            # Simple timezone to country mapping
            if "Europe" in account.timezone:
                country_code = "GB"
            elif "America/New_York" in account.timezone:
                country_code = "US"

        # Calculate tax with Stripe
        response = stripe.tax.Calculation.create(
            currency=currency.lower(),
            line_items=line_items,
            customer_details={
                "address": {
                    "country": country_code,
                },
                "tax_ids": [
                    {
                        "type": "eu_vat" if account.vat_id else "us_ein",
                        "value": account.vat_id or account.tax_id or "00-0000000",
                    }
                ] if (account.vat_id or account.tax_id) else [],
            },
        )

        # Extract tax amount
        tax_amount = response.get("tax_amount_exclusive", 0)
        tax_breakdown = response.get("tax_breakdown", [])

        # Calculate rate
        tax_rate = Decimal(str(tax_amount)) / Decimal(str(amount)) if amount > 0 else Decimal("0")

        logger.info(
            "stripe_tax_calculated",
            account_id=str(account.id),
            amount=amount,
            tax_amount=tax_amount,
            tax_rate=float(tax_rate),
        )

        return {
            "amount": tax_amount,
            "rate": tax_rate,
            "breakdown": tax_breakdown,
            "provider": "stripe_tax",
        }

    async def _calculate_simple_tax(self, account: Account, amount: int) -> dict[str, Any]:
        """
        Fallback simple tax calculation.

        Args:
            account: Account to calculate tax for
            amount: Amount in cents

        Returns:
            Simple tax calculation
        """
        # Skip tax for tax-exempt accounts
        if account.tax_exempt:
            return {
                "amount": 0,
                "rate": Decimal("0"),
                "breakdown": [],
                "reason": "tax_exempt",
            }

        # Apply simple 10% tax rate
        tax_rate = Decimal("0.10")
        tax_amount = int(Decimal(str(amount)) * tax_rate)

        logger.info(
            "simple_tax_calculated",
            account_id=str(account.id),
            amount=amount,
            tax_amount=tax_amount,
            tax_rate=float(tax_rate),
        )

        return {
            "amount": tax_amount,
            "rate": tax_rate,
            "breakdown": [],
            "provider": "simple",
        }
