from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress
from typing import Any


class RoomEventStreamService:
    # 折叠态 trace-card 只显示数量、不渲染这些“仅展开可见”的高频重负载事件正文。
    # SSE 历史回放时剥离它们的大字段（前端进入会话即全量加载会卡顿），前端展开某条
    # trace 时再按 run_id 拉取全量（GET /api/im/runs/{run_id}/events）。实时事件不剥离。
    _TRUNCATE_EVENT_NAMES = frozenset(
        {
            "tool.called",
            "tool.succeeded",
            "tool.failed",
            "tool.retrying",
            "llm.completed",
            "agent.think",
            "agent.tool.reasoning",
        }
    )
    _TRUNCATE_PAYLOAD_KEYS = ("respond", "content", "arguments", "think", "reasoning", "delta")

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

    def no_store_publish(self, room_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """只向在线订阅者推送、不落库。

        用于 agent.delta 这类高频流式增量：逐 chunk 同步 insert_one 会阻塞 asyncio 事件循环，
        且会被 SSE 重连时全量重放。最终结果另由 agent.final + 落库消息承载，故增量无需持久化。
        """
        event = {
            "event_id": str(uuid.uuid4()),
            "scope_id": room_id,
            "room_id": room_id,
            "name": name,
            "payload": payload,
            "created_at": time.time(),
        }
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
                    yield self.format_sse(self._truncate_for_history(event))

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

    def _truncate_for_history(self, event: dict[str, Any]) -> dict[str, Any]:
        """历史回放时剥离“仅展开可见”重负载事件的大字段，标记 truncated=True。

        只命中 _TRUNCATE_EVENT_NAMES 里的 runtime trace 事件；房间消息类事件
        （message.created / run.created 等）名称不在集合内，原样返回不受影响。
        仅当确有大字段被剥离时才标记 truncated，避免前端对空负载事件做无谓的全量拉取。
        """
        if event.get("name") not in self._TRUNCATE_EVENT_NAMES:
            return event
        payload = event.get("payload")
        if not isinstance(payload, dict) or not any(
            key in payload for key in self._TRUNCATE_PAYLOAD_KEYS
        ):
            return event
        trimmed = {k: v for k, v in payload.items() if k not in self._TRUNCATE_PAYLOAD_KEYS}
        return {**event, "payload": trimmed, "truncated": True}

    def format_sse(self, event: dict[str, Any]) -> str:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        return f"event: {event['name']}\ndata: {payload}\n\n"

    def _event_from_sse(self, raw: str) -> dict[str, Any] | None:
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line.removeprefix("data:").strip())
        return None
