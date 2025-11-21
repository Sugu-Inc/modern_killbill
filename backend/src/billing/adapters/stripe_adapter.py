"""Stripe payment gateway adapter."""
import stripe
from typing import Any

from billing.config import settings


class StripeAdapter:
    """Adapter for Stripe payment gateway integration."""

    def __init__(self):
        """Initialize Stripe adapter with API key."""
        stripe.api_key = settings.stripe_secret_key

    async def create_customer(self, email: str, name: str, metadata: dict[str, Any] | None = None) -> str:
        """
        Create a Stripe customer.

        Args:
            email: Customer email
            name: Customer name
            metadata: Additional metadata

        Returns:
            Stripe customer ID
        """
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata=metadata or {},
        )
        return customer.id

    async def attach_payment_method(
        self, customer_id: str, payment_method_id: str, set_default: bool = False
    ) -> dict[str, Any]:
        """
        Attach payment method to customer.

        Args:
            customer_id: Stripe customer ID
            payment_method_id: Stripe payment method ID
            set_default: Set as default payment method

        Returns:
            Payment method details
        """
        # Attach payment method to customer
        payment_method = stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer_id,
        )

        # Set as default if requested
        if set_default:
            stripe.Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": payment_method_id},
            )

        return {
            "id": payment_method.id,
            "type": payment_method.type,
            "card": {
                "last4": payment_method.card.last4 if payment_method.card else None,
                "exp_month": payment_method.card.exp_month if payment_method.card else None,
                "exp_year": payment_method.card.exp_year if payment_method.card else None,
            }
            if payment_method.card
            else None,
        }

    async def detach_payment_method(self, payment_method_id: str) -> None:
        """
        Detach payment method from customer.

        Args:
            payment_method_id: Stripe payment method ID
        """
        stripe.PaymentMethod.detach(payment_method_id)

    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        customer_id: str,
        payment_method_id: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a payment intent.

        Args:
            amount: Amount in cents
            currency: ISO currency code
            customer_id: Stripe customer ID
            payment_method_id: Stripe payment method ID (optional, uses default if None)
            idempotency_key: Idempotency key for retries
            metadata: Additional metadata

        Returns:
            Payment intent details
        """
        params: dict[str, Any] = {
            "amount": amount,
            "currency": currency.lower(),
            "customer": customer_id,
            "confirm": True,
            "metadata": metadata or {},
        }

        if payment_method_id:
            params["payment_method"] = payment_method_id
        else:
            # Use customer's default payment method
            params["payment_method_types"] = ["card"]

        if idempotency_key:
            params["idempotency_key"] = idempotency_key

        try:
            payment_intent = stripe.PaymentIntent.create(**params)

            return {
                "id": payment_intent.id,
                "status": payment_intent.status,
                "amount": payment_intent.amount,
                "currency": payment_intent.currency,
                "client_secret": payment_intent.client_secret,
            }
        except stripe.error.CardError as e:
            # Card was declined
            return {
                "id": None,
                "status": "failed",
                "error": e.user_message,
            }
        except stripe.error.StripeError as e:
            # Other Stripe error
            return {
                "id": None,
                "status": "failed",
                "error": str(e),
            }

    async def retrieve_payment_intent(self, payment_intent_id: str) -> dict[str, Any]:
        """
        Retrieve payment intent status.

        Args:
            payment_intent_id: Stripe payment intent ID

        Returns:
            Payment intent details
        """
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)

        return {
            "id": payment_intent.id,
            "status": payment_intent.status,
            "amount": payment_intent.amount,
            "currency": payment_intent.currency,
        }

    async def create_invoice(
        self,
        customer_id: str,
        line_items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a Stripe invoice.

        Args:
            customer_id: Stripe customer ID
            line_items: Invoice line items
            metadata: Additional metadata

        Returns:
            Invoice details
        """
        # Create invoice items
        for item in line_items:
            stripe.InvoiceItem.create(
                customer=customer_id,
                amount=item["amount"],
                currency=item["currency"],
                description=item["description"],
            )

        # Create invoice
        invoice = stripe.Invoice.create(
            customer=customer_id,
            metadata=metadata or {},
            auto_advance=True,  # Auto-finalize
        )

        return {
            "id": invoice.id,
            "number": invoice.number,
            "status": invoice.status,
            "amount_due": invoice.amount_due,
            "currency": invoice.currency,
        }

    async def finalize_invoice(self, invoice_id: str) -> dict[str, Any]:
        """
        Finalize a draft invoice.

        Args:
            invoice_id: Stripe invoice ID

        Returns:
            Invoice details
        """
        invoice = stripe.Invoice.finalize_invoice(invoice_id)

        return {
            "id": invoice.id,
            "number": invoice.number,
            "status": invoice.status,
            "amount_due": invoice.amount_due,
        }

    async def pay_invoice(self, invoice_id: str) -> dict[str, Any]:
        """
        Pay an invoice.

        Args:
            invoice_id: Stripe invoice ID

        Returns:
            Payment result
        """
        try:
            invoice = stripe.Invoice.pay(invoice_id)

            return {
                "id": invoice.id,
                "status": invoice.status,
                "paid": invoice.paid,
                "amount_paid": invoice.amount_paid,
            }
        except stripe.error.CardError as e:
            return {
                "id": invoice_id,
                "status": "payment_failed",
                "paid": False,
                "error": e.user_message,
            }

    async def construct_webhook_event(self, payload: bytes, signature: str) -> Any:
        """
        Construct and verify webhook event.

        Args:
            payload: Webhook payload
            signature: Webhook signature

        Returns:
            Stripe event object

        Raises:
            ValueError: If signature verification fails
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.stripe_webhook_secret
            )
            return event
        except ValueError as e:
            raise ValueError(f"Invalid payload: {e}") from e
        except stripe.error.SignatureVerificationError as e:
            raise ValueError(f"Invalid signature: {e}") from e
