from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db_session
from api.schemas.analytics import EventBatchCreate, EventCreate, EventResponse
from api.services.analytics import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record analytics event",
    description="Captures client-side customer interaction, product view, or funnel step.",
)
async def record_event(
    payload: EventCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> EventResponse:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    event = await analytics_service.record_event(
        db=db,
        event_in=payload,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return EventResponse.model_validate(event)


@router.post(
    "/events/batch",
    response_model=list[EventResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Batch record analytics events",
    description="Captures multiple queued storefront interactions in a single network roundtrip.",
)
async def record_events_batch(
    payload: EventBatchCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[EventResponse]:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    events = await analytics_service.record_events_batch(
        db=db,
        events_in=payload.events,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return [EventResponse.model_validate(e) for e in events]
