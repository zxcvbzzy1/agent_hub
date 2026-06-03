from __future__ import annotations

from typing import Any

from im_backend.application.services._shared.lookup import require_im_message
from im_backend.application.services._shared.message_text import message_text as extract_message_text
from im_backend.application.services.messaging.agents import IMAgentService
from im_backend.application.services.platform.events import RoomEventStreamService
from im_backend.application.services.messaging.rooms import RoomService
from im_backend.domain.models import ContentPart, Message
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class GroupMessageService:
    def __init__(
        self,
        *,
        store,
        bridge: AgentFlowBridge,
        events: RoomEventStreamService,
        rooms: RoomService,
        agents: IMAgentService,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = events
        self._rooms = rooms
        self._agents = agents

    def list_messages(self, room_id: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
        self._rooms.ensure_group_room(room_id)
        messages = self._store.find_many(
            "im_messages",
            {"room_id": room_id},
            sort=[("created_at", 1)],
        )
        if conversation_id is not None:
            messages = [m for m in messages if m.get("conversation_id") == conversation_id]
        return messages

    def get_message(self, message_id: str) -> dict[str, Any]:
        return require_im_message(self._store, message_id)

    def add_message(
        self,
        *,
        room_id: str,
        sender_type: str,
        sender_id: str,
        content_parts: list[dict[str, Any]],
        conversation_id: str = "",
        mentions: list[str] | None = None,
        reply_to: str = "",
        quote_of: str = "",
        run_id: str = "",
        status: str = "sent",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        room = self._rooms.ensure_group_room(room_id)
        parts = [ContentPart.from_dict(part) for part in content_parts]
        if not parts:
            raise ValueError("content_parts 不能为空")
        for agent_id in mentions or []:
            if agent_id not in room.get("member_agent_ids", []):
                raise ValueError(f"被 @ 的 agent 不在房间中: {agent_id}")

        message = Message.create(
            room_id=room_id,
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content_parts=parts,
            mentions=mentions or [],
            reply_to=reply_to,
            quote_of=quote_of,
            run_id=run_id,
            status=status,
            metadata=metadata or {},
        )
        record = self._store.insert_one("im_messages", message.to_dict())
        self._store.update_one("im_rooms", {"room_id": room_id}, {"updated_at": record["created_at"]})
        self._events.publish(room_id, "message.created", {"message": record})
        return record

    def list_agent_messages(self, agent_id: str, user_id: str = "") -> list[dict[str, Any]]:
        if user_id:
            self._agents.ensure_agent_access(agent_id, user_id)
        else:
            self._bridge.ensure_agent_exists(agent_id)
        rooms = self._store.find_many("im_rooms", {"type": "group"})
        group_room_ids = {
            room.get("room_id")
            for room in rooms
            if agent_id in (room.get("member_agent_ids") or [])
        }
        conversation_ids = {
            conversation.get("conversation_id")
            for conversation in self._store.find_many("im_conversations", {"agent_id": agent_id})
        }
        messages = [
            message
            for message in self._store.find_many("im_messages", sort=[("created_at", -1)])
            if message.get("room_id") in group_room_ids
            or message.get("conversation_id") in conversation_ids
            or message.get("sender_id") == agent_id
            or agent_id in (message.get("mentions") or [])
        ]
        return messages[:50]

    def message_text(self, message: dict[str, Any]) -> str:
        return extract_message_text(message)
