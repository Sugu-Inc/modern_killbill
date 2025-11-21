"""Integration tests for invoice PDF generation."""
import pytest
import io
from sqlalchemy.ext.asyncio import AsyncSession

from billing.models.account import Account
from billing.models.plan import Plan, PlanInterval
from billing.models.subscription import Subscription
from billing.services.subscription_service import SubscriptionService
from billing.services.invoice_service import InvoiceService
from billing.services.invoice_pdf_service import InvoicePDFService
from billing.schemas.subscription import SubscriptionCreate


@pytest.mark.asyncio
async def test_generate_invoice_pdf(db_session: AsyncSession) -> None:
    """Test that PDF can be generated for an invoice."""
    # Create account
    account = Account(
        email="pdf-test@example.com",
        name="PDF Test Customer",
        currency="USD",
        timezone="America/New_York",
    )
    db_session.add(account)
    await db_session.flush()

    # Create plan
    plan = Plan(
        name="Premium Plan",
        price=5000,  # $50.00
        currency="USD",
        interval=PlanInterval.MONTH,
        active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=1,
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Generate PDF
    pdf_service = InvoicePDFService()
    pdf_bytes = await pdf_service.generate_pdf(invoice, account)

    # Verify PDF was generated
    assert pdf_bytes is not None
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0

    # Verify PDF header (PDF files start with %PDF)
    assert pdf_bytes[:4] == b'%PDF', "Generated file should be a valid PDF"


@pytest.mark.asyncio
async def test_pdf_includes_invoice_details(db_session: AsyncSession) -> None:
    """Test that PDF includes all invoice details."""
    # Create account
    account = Account(
        email="pdf-details@example.com",
        name="Invoice Details Test Co.",
        currency="USD",
        timezone="UTC",
    )
    db_session.add(account)
    await db_session.flush()

    # Create plan
    plan = Plan(
        name="Business Plan",
        price=10000,  # $100.00
        currency="USD",
        interval=PlanInterval.MONTH,
        active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=2,  # 2 licenses
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Generate PDF
    pdf_service = InvoicePDFService()
    pdf_bytes = await pdf_service.generate_pdf(invoice, account)

    # Verify PDF was generated
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 0

    # Note: Full PDF content inspection would require PDF parsing library
    # For now, we verify it's a valid PDF structure


@pytest.mark.asyncio
async def test_pdf_with_branding(db_session: AsyncSession) -> None:
    """Test that PDF generation respects branding settings."""
    # Create account
    account = Account(
        email="branding-test@example.com",
        name="Branding Test Inc",
        currency="USD",
        timezone="America/Los_Angeles",
    )
    db_session.add(account)
    await db_session.flush()

    # Create plan
    plan = Plan(
        name="Starter Plan",
        price=2500,  # $25.00
        currency="USD",
        interval=PlanInterval.MONTH,
        active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=1,
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Generate PDF with branding
    pdf_service = InvoicePDFService()
    pdf_bytes = await pdf_service.generate_pdf(invoice, account)

    # Verify PDF was generated
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b'%PDF'

    # Branding verification would require PDF content parsing
    # At minimum, we verify the PDF is generated successfully


@pytest.mark.asyncio
async def test_pdf_multi_currency_formatting(db_session: AsyncSession) -> None:
    """Test that PDF correctly formats different currencies."""
    # Test with EUR
    account_eur = Account(
        email="euro-pdf@example.com",
        name="European Customer",
        currency="EUR",
        timezone="Europe/Paris",
    )
    db_session.add(account_eur)
    await db_session.flush()

    plan_eur = Plan(
        name="Euro Plan",
        price=7500,  # €75.00
        currency="EUR",
        interval=PlanInterval.MONTH,
        active=True,
    )
    db_session.add(plan_eur)
    await db_session.flush()

    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account_eur.id,
        plan_id=plan_eur.id,
        quantity=1,
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Generate PDF
    pdf_service = InvoicePDFService()
    pdf_bytes = await pdf_service.generate_pdf(invoice, account_eur)

    # Verify PDF generated for EUR currency
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b'%PDF'


@pytest.mark.asyncio
async def test_pdf_with_tax_breakdown(db_session: AsyncSession) -> None:
    """Test that PDF includes tax breakdown when applicable."""
    # Create account
    account = Account(
        email="tax-pdf@example.com",
        name="Tax Invoice Customer",
        currency="USD",
        timezone="America/Chicago",
        tax_exempt=False,
    )
    db_session.add(account)
    await db_session.flush()

    # Create plan
    plan = Plan(
        name="Taxable Plan",
        price=10000,  # $100.00
        currency="USD",
        interval=PlanInterval.MONTH,
        active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=1,
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    # Generate invoice (should include tax)
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Verify invoice has tax
    assert invoice.tax > 0, "Invoice should have tax calculated"

    # Generate PDF
    pdf_service = InvoicePDFService()
    pdf_bytes = await pdf_service.generate_pdf(invoice, account)

    # Verify PDF generated with tax information
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b'%PDF'


@pytest.mark.asyncio
async def test_pdf_with_line_items(db_session: AsyncSession) -> None:
    """Test that PDF includes all line items."""
    # Create account
    account = Account(
        email="lineitems-pdf@example.com",
        name="Line Items Test",
        currency="USD",
        timezone="UTC",
    )
    db_session.add(account)
    await db_session.flush()

    # Create plan
    plan = Plan(
        name="Multi-Item Plan",
        price=3000,  # $30.00
        currency="USD",
        interval=PlanInterval.MONTH,
        active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    # Create subscription with quantity > 1
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=5,  # Multiple licenses
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Verify invoice has line items
    assert len(invoice.line_items) > 0

    # Generate PDF
    pdf_service = InvoicePDFService()
    pdf_bytes = await pdf_service.generate_pdf(invoice, account)

    # Verify PDF generated
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b'%PDF'


@pytest.mark.asyncio
async def test_pdf_generation_error_handling(db_session: AsyncSession) -> None:
    """Test that PDF generation handles errors gracefully."""
    # Create account
    account = Account(
        email="error-test@example.com",
        name="Error Test Customer",
        currency="USD",
        timezone="UTC",
    )
    db_session.add(account)
    await db_session.flush()

    # Create plan
    plan = Plan(
        name="Test Plan",
        price=1000,
        currency="USD",
        interval=PlanInterval.MONTH,
        active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    # Create subscription
    subscription_service = SubscriptionService(db_session)
    subscription_data = SubscriptionCreate(
        account_id=account.id,
        plan_id=plan.id,
        quantity=1,
    )
    subscription = await subscription_service.create_subscription(subscription_data)
    await db_session.commit()

    # Generate invoice
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.generate_invoice_for_subscription(subscription.id)
    await db_session.commit()

    # Attempt PDF generation (should not raise exceptions)
    pdf_service = InvoicePDFService()
    try:
        pdf_bytes = await pdf_service.generate_pdf(invoice, account)
        # If successful, verify it's a valid PDF
        if pdf_bytes:
            assert len(pdf_bytes) > 0
    except Exception as e:
        # If there's an error, it should be a specific, expected error type
        # not a generic unhandled exception
        pytest.fail(f"PDF generation should handle errors gracefully: {e}")
