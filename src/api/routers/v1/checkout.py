from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.schemas.order import QuoteRequest, QuoteResponse
from api.services.order import OrderService

router = APIRouter(prefix="/checkout", tags=["Checkout"])


@router.post("/quote", response_model=QuoteResponse)
async def get_checkout_quote(
    payload: QuoteRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> QuoteResponse:
    """Calculates live checkout quote, inventory availability, and delivery pricing."""
    return await OrderService.calculate_quote(db, payload)
