import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.models import User
from app.services.notifications import notification_manager

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/subscribe")
async def subscribe(request: Request, current_user: User = Depends(get_current_user)) -> StreamingResponse:
    queue = notification_manager.subscribe(current_user.id)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: proposal-update\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            notification_manager.unsubscribe(current_user.id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
