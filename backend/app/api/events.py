"""HTTP and Server-Sent Event APIs for Odin events."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.events.bus import event_bus


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


@router.get("/")
def list_events(
    event_type: str | None = None,
    source: str | None = None,
    correlation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    events = event_bus.history(
        event_type=event_type,
        source=source,
        correlation_id=correlation_id,
        limit=limit,
    )

    return {
        "count": len(events),
        "events": [
            event.to_dict()
            for event in events
        ],
    }


@router.get("/stream")
async def stream_events(
    request: Request,
    last_event_id: str | None = None,
):
    async def event_generator() -> AsyncIterator[str]:
        cursor = last_event_id

        yield "retry: 3000\n\n"

        while True:
            if await request.is_disconnected():
                break

            events = await asyncio.to_thread(
                event_bus.wait_for_events,
                cursor,
                timeout=15.0,
                limit=100,
            )

            if not events:
                yield ": keep-alive\n\n"
                continue

            for event in events:
                cursor = event.id
                data = json.dumps(
                    event.to_dict(),
                    default=str,
                )

                yield (
                    f"id: {event.id}\n"
                    f"event: {event.type}\n"
                    f"data: {data}\n\n"
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
