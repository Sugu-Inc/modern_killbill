"""Payment endpoints for payment processing and management."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from billing.api.deps import get_db
from billing.models.payment import PaymentStatus
from billing.schemas.payment import PaymentResponse, PaymentRetryResponse
from billing.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=dict)
async def list_payments(
    invoice_id: Optional[UUID] = Query(None, description="Filter by invoice ID"),
    status_filter: Optional[PaymentStatus] = Query(None, alias="status", description="Filter by payment status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Results per page"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List payments with optional filters.

    - **invoice_id**: Filter by specific invoice
    - **status**: Filter by payment status (pending, succeeded, failed, cancelled)
    - **page**: Page number for pagination
    - **page_size**: Number of results per page
    """
    service = PaymentService(db)

    try:
        payments = await service.list_payments(
            invoice_id=invoice_id,
            status=status_filter,
            page=page,
            page_size=page_size,
        )

        return {
            "items": [PaymentResponse.model_validate(p) for p in payments],
            "total": len(payments),  # In production, do a count query
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list payments: {str(e)}",
        ) from e


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """
    Get payment details by ID.

    Returns payment information including status, amount, and transaction details.
    """
    service = PaymentService(db)

    try:
        payment = await service.get_payment(payment_id)

        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment {payment_id} not found",
            )

        return PaymentResponse.model_validate(payment)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get payment: {str(e)}",
        ) from e


@router.post("/{payment_id}/retry", response_model=PaymentResponse)
async def retry_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """
    Manually retry a failed payment.

    Can only retry payments in FAILED status. Will increment retry count
    and attempt to charge the payment method again.
    """
    service = PaymentService(db)

    try:
        payment = await service.retry_payment(payment_id)
        await db.commit()

        return PaymentResponse.model_validate(payment)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry payment: {str(e)}",
        ) from e


@router.get("/{payment_id}/retry-schedule", response_model=List[PaymentRetryResponse])
async def get_retry_schedule(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> List[PaymentRetryResponse]:
    """
    Get retry schedule for a payment.

    Returns the schedule of retry attempts (days 3, 5, 7, 10 after initial failure).
    """
    service = PaymentService(db)

    try:
        schedule = await service.get_retry_schedule(payment_id)
        return schedule
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get retry schedule: {str(e)}",
        ) from e
