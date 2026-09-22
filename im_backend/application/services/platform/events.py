from __future__ import annotations

import time
import uuid
from typing import Any
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
ensure_agent_flow_path()
from infra.runtime import RedisRuntime

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

    def __init__(self, store, runtime=None) -> None:
        
        self._store = store
        self.runtime = runtime or RedisRuntime()

    async def publish(self, room_id, name, payload):
        event = self._event(room_id, name, payload)
        self._store.insert_one("im_events", event)
        await self.runtime.append("scope", room_id, event)
        return event

    async def no_store_publish(self, room_id, name, payload):
        event = self._event(room_id, name, payload)
        await self.runtime.append("scope", room_id, event)
        return event

    def _event(self, room_id, name, payload):
        return dict(event_id=str(uuid.uuid4()), scope_id=room_id, room_id=room_id,
                    name=name, payload=payload, created_at=time.time())

    def list_events(self, room_id):
        return self._store.find_many("im_events", {"scope_id": room_id}, sort=[("created_at", 1)]) or self._store.find_many(
            "im_events", {"room_id": room_id}, sort=[("created_at", 1)])

    async def stream(self, room_id, last_id=None):
        async for raw in self.runtime.stream("scope", room_id, lambda: self.list_events(room_id), last_id=last_id):
            yield raw

    async def stream_merged(self, scope_id, *, runtime_events, runtime_ids_provider, last_id=None):
        def history():
            events = self.list_events(scope_id)
            for run_id in runtime_ids_provider():
                events.extend(runtime_events.list_events(run_id))
            return events

        async for raw in self.runtime.stream("scope", scope_id, history, last_id=last_id,
                                             transform=self._truncate_for_history):
            yield raw

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

    def format_sse(self, event, cursor=None):
        return self.runtime.sse(event, cursor)
