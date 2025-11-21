"""Credit management API endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from billing.database import get_db
from billing.services.credit_service import CreditService
from billing.schemas.credit import CreditCreate, Credit

router = APIRouter(prefix="/credits", tags=["credits"])


@router.post("", response_model=Credit, status_code=status.HTTP_201_CREATED)
async def create_credit(
    credit_data: CreditCreate,
    db: AsyncSession = Depends(get_db),
) -> Credit:
    """
    Create a new credit for an account.

    Credits can be created for:
    - Customer satisfaction (goodwill)
    - Refunds
    - Promotional credits
    - Service outage compensation

    The credit will automatically apply to the next invoice generated
    for the account.
    """
    credit_service = CreditService(db)

    try:
        credit = await credit_service.create_credit(credit_data)
        await db.commit()
        return credit
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create credit: {str(e)}",
        )
