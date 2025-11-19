"""Invoice API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db
from billing.models.invoice import InvoiceStatus
from billing.schemas.invoice import Invoice, InvoiceList, InvoiceVoid
from billing.services.invoice_service import InvoiceService

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
