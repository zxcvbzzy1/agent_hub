from __future__ import annotations

from typing import Any

from im_backend.application.services.events import RoomEventStreamService
from im_backend.domain.models import MessageAction


class MessageActionService:
    def __init__(self, *, store, events: RoomEventStreamService) -> None:
        self._store = store
        self._events = events

    def get_message(self, message_id: str) -> dict[str, Any]:
        message = self._store.find_one("im_messages", {"message_id": message_id})
        if message is None:
            raise KeyError(f"消息不存在: {message_id}")
        return message

    def record_action(
        self,
        *,
        message_id: str,
        action_type: str,
        actor_id: str = "user",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = self.get_message(message_id)
        action = MessageAction.create(
            message_id=message_id,
            action_type=action_type,
            actor_id=actor_id,
            payload=payload or {},
            status="approved" if action_type == "approve" else "recorded",
        )
        record = self._store.insert_one("im_message_actions", action.to_dict())
        stream_id = message.get("room_id") or message.get("conversation_id")
        self._events.publish(
            stream_id,
            "message.action",
            {"message_id": message_id, "action": record},
        )
        return record
