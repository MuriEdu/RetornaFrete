import asyncio
import json
import uuid
from collections import defaultdict


class NotificationManager:
    def __init__(self) -> None:
        self.listeners: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)

    def subscribe(self, user_id: uuid.UUID) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        self.listeners[str(user_id)].append(queue)
        return queue

    def unsubscribe(self, user_id: uuid.UUID, queue: asyncio.Queue[str]) -> None:
        listeners = self.listeners.get(str(user_id), [])
        if queue in listeners:
            listeners.remove(queue)

    async def publish_proposal_update(self, user_ids: list[uuid.UUID], payload: dict) -> None:
        message = json.dumps(payload, default=str)
        for user_id in user_ids:
            for queue in list(self.listeners.get(str(user_id), [])):
                await queue.put(message)


notification_manager = NotificationManager()
