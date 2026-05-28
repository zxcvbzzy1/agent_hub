from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress
from typing import Any


class RoomEventStreamService:
    def __init__(self, store) -> None:
        self._store = store
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}

    def publish(self, room_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "scope_id": room_id,
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
        events = self._store.find_many(
            "im_events",
            {"scope_id": room_id},
            sort=[("created_at", 1)],
        )
        if events:
            return events
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

    async def stream_merged(self, scope_id: str, *, runtime_events, runtime_ids_provider):
        im_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        runtime_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        runtime_tasks: dict[str, asyncio.Task] = {}
        seen_event_ids: set[str] = set()
        self._queues.setdefault(scope_id, []).append(im_queue)

        def remember(event: dict[str, Any]) -> bool:
            event_id = event.get("event_id")
            if not event_id:
                event_id = f"{event.get('name')}:{event.get('created_at')}:{json.dumps(event.get('payload', {}), sort_keys=True, default=str)}"
            if event_id in seen_event_ids:
                return False
            seen_event_ids.add(event_id)
            return True

        async def pump_runtime(run_id: str) -> None:
            async for raw in runtime_events.stream(run_id):
                event = self._event_from_sse(raw)
                if event is not None:
                    await runtime_queue.put(event)

        def ensure_runtime_pump(run_id: str) -> None:
            if not run_id or run_id in runtime_tasks:
                return
            runtime_tasks[run_id] = asyncio.create_task(pump_runtime(run_id))

        try:
            runtime_ids = set(runtime_ids_provider())
            history = self.list_events(scope_id)
            for run_id in runtime_ids:
                history.extend(runtime_events.list_events(run_id))
                ensure_runtime_pump(run_id)
            for event in sorted(history, key=lambda item: item.get("created_at") or 0):
                if remember(event):
                    yield self.format_sse(event)

            while True:
                im_task = asyncio.create_task(im_queue.get())
                runtime_task = asyncio.create_task(runtime_queue.get())
                done, pending = await asyncio.wait(
                    {im_task, runtime_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in pending:
                    with suppress(asyncio.CancelledError):
                        await task
                for task in done:
                    event = task.result()
                    if event.get("name") == "run.created":
                        run = event.get("payload", {}).get("run", {})
                        ensure_runtime_pump(run.get("run_id", ""))
                    for run_id in runtime_ids_provider():
                        ensure_runtime_pump(run_id)
                    if remember(event):
                        yield self.format_sse(event)
        finally:
            queues = self._queues.get(scope_id, [])
            if im_queue in queues:
                queues.remove(im_queue)
            for task in runtime_tasks.values():
                task.cancel()
            for task in runtime_tasks.values():
                with suppress(asyncio.CancelledError):
                    await task

    def format_sse(self, event: dict[str, Any]) -> str:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        return f"event: {event['name']}\ndata: {payload}\n\n"

    def _event_from_sse(self, raw: str) -> dict[str, Any] | None:
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line.removeprefix("data:").strip())
        return None
