from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any


class RoomEventStreamService:
    def __init__(self, store) -> None:
        self._store = store
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}

    def publish(self, room_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "room_id": room_id,
            "name": name,
            "payload": payload,
            "created_at": time.time(),
        }
        self._store.insert_one("im_events", event)
        for queue in list(self._queues.get(room_id, [])):
            queue.put_nowait(event)
        return event

    def list_events(self, room_id: str) -> list[dict[str, Any]]:
        return self._store.find_many(
            "im_events",
            {"room_id": room_id},
            sort=[("created_at", 1)],
        )

    async def stream(self, room_id: str):
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.setdefault(room_id, []).append(queue)
        try:
            for event in self.list_events(room_id):
                yield self.format_sse(event)
            while True:
                event = await queue.get()
                yield self.format_sse(event)
        finally:
            queues = self._queues.get(room_id, [])
            if queue in queues:
                queues.remove(queue)

    def format_sse(self, event: dict[str, Any]) -> str:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        return f"event: {event['name']}\ndata: {payload}\n\n"

