from __future__ import annotations

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
ensure_agent_flow_path()
from application.services.events import EventStreamService, scope_delivery


class RoomEventStreamService:
    """Business notifications only; execution details are queried through run APIs."""

    def __init__(self, store, runtime=None):
        self._store = store
        self._events = EventStreamService(store, runtime)
        self.runtime = self._events.runtime

    async def publish(self, room_id, name, payload):
        return await self._events.publish_scope(room_id, name, payload)

    async def no_store_publish(self, room_id, name, payload):
        # Business events are durable; transient model deltas belong to run streams.
        return await self.publish(room_id, name, payload)

    async def list_events(self, room_id, *, user_id='service'):
        return await self.runtime.journal.events('scope', room_id, user_id=user_id)

    async def stream(self, room_id, last_id=None, *, user_id='service'):
        async for raw in self.runtime.stream('scope', room_id,
                lambda: self.runtime.journal.history('scope', room_id),
                last_id=last_id, transform=scope_delivery, user_id=user_id):
            yield raw

    async def get_event(self, scope_id, event_id, *, user_id='service'):
        return next((e for e in await self.list_events(scope_id, user_id=user_id) if e['event_id'] == event_id), None)

    def format_sse(self, event, cursor=None):
        return self.runtime.sse(event, cursor)
