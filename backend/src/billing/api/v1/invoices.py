"""Invoice API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db
from billing.models.invoice import InvoiceStatus
from billing.schemas.invoice import Invoice, InvoiceList, InvoiceVoid
from billing.services.invoice_service import InvoiceService
from billing.services.invoice_pdf_service import InvoicePDFService
from billing.services.account_service import AccountService

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get("", response_model=InvoiceList)
async def list_invoices(
    account_id: UUID | None = Query(default=None, description="Filter by account ID"),
    subscription_id: UUID | None = Query(default=None, description="Filter by subscription ID"),
    status: InvoiceStatus | None = Query(default=None, description="Filter by status"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=100, ge=1, le=1000, description="Items per page (max 1000)"),
    db: AsyncSession = Depends(get_db),
) -> InvoiceList:
    """
    List invoices with pagination and filtering.

    Filter invoices by:
    - **account_id**: Account UUID (optional)
    - **subscription_id**: Subscription UUID (optional)
    - **status**: Invoice status (draft, open, paid, void, past_due) (optional)

    Supports pagination with:
    - **page**: Page number (1-indexed, default: 1)
    - **page_size**: Items per page (default: 100, max: 1000)

    Returns invoices ordered by creation date (newest first).
    """
    service = InvoiceService(db)
    invoices, total = await service.list_invoices(
        account_id=account_id,
        subscription_id=subscription_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    return InvoiceList(
        items=invoices,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{invoice_id}", response_model=Invoice)
async def get_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Invoice:
    """
    Get invoice by ID.

    Returns detailed invoice information including:
    - Invoice number and status
    - Amount due, amount paid, and tax
    - Line items breakdown
    - Associated account and subscription
    - Payment history (via relationships)

    **Status Meanings**:
    - **draft**: Invoice is being prepared
    - **open**: Invoice is issued and awaiting payment
    - **paid**: Invoice has been fully paid
    - **void**: Invoice has been cancelled
    - **past_due**: Invoice is overdue for payment
    """
    service = InvoiceService(db)
    invoice = await service.get_invoice(invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found",
        )

    return invoice


@router.post("/{invoice_id}/void", response_model=Invoice)
async def void_invoice(
    invoice_id: UUID,
    void_data: InvoiceVoid,
    db: AsyncSession = Depends(get_db),
) -> Invoice:
    """
    Void an invoice (cancel it).

    Use this to cancel an unpaid invoice. Provide a reason for the void operation.

    **Important**:
    - Only invoices with status **draft**, **open**, or **past_due** can be voided
    - **Paid** invoices cannot be voided - issue a credit instead
    - Voiding is permanent and cannot be undone

    **Use Cases**:
    - Customer cancels before payment
    - Billing error requires invoice cancellation
    - Subscription cancelled before first payment

    **After Voiding**:
    - Invoice status changes to **void**
    - Invoice is marked with void timestamp
    - Reason is stored in metadata
    - Invoice still appears in history but is not payable
    """
    service = InvoiceService(db)

    try:
        invoice = await service.void_invoice(invoice_id, void_data.reason)
        await db.commit()
        return invoice
    except ValueError as e:
        await db.rollback()
        # Determine appropriate HTTP status code
        error_msg = str(e)
        if "not found" in error_msg:
            status_code = status.HTTP_404_NOT_FOUND
        elif "already voided" in error_msg or "paid" in error_msg:
            status_code = status.HTTP_400_BAD_REQUEST
        else:
            status_code = status.HTTP_400_BAD_REQUEST

        raise HTTPException(status_code=status_code, detail=error_msg) from e


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Generate and download invoice as PDF.

    Returns a professionally-formatted PDF invoice with:
    - Company branding (logo, colors)
    - Invoice details (number, date, due date, status)
    - Customer billing information
    - Detailed line items breakdown
    - Tax calculation (if applicable)
    - Payment status and amount due

    The PDF is generated dynamically using the configured branding settings.

    **Response**:
    - Content-Type: application/pdf
    - Content-Disposition: attachment with invoice filename

    **Use Cases**:
    - Customer wants to download invoice for records
    - Accounting systems need PDF copies
    - Email invoice PDF to customer
    - Print invoice for physical mailing
    """
    # Get invoice
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice(invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found",
        )

    # Get account for billing information
    account_service = AccountService(db)
    account = await account_service.get_account(invoice.account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {invoice.account_id} not found",
        )

    try:
        # Generate PDF
        pdf_service = InvoicePDFService()
        pdf_bytes = await pdf_service.generate_pdf(invoice, account)

        # Return PDF as downloadable file
        filename = f"invoice-{invoice.number}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}",
        ) from e
