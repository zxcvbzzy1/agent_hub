from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from im_backend.application.event_stream import RoomEventStreamService
from im_backend.domain.models import ContentPart, Conversation, Message
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class ConversationService:
    """Single-agent conversation use cases.

    A conversation is not a room. It is the single-agent context boundary used
    to rebuild HistoryProvider input before each direct agent reply.
    """

    def __init__(
        self,
        *,
        store,
        bridge: AgentFlowBridge,
        events: RoomEventStreamService,
        default_workdir: str | Path,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = events
        self._default_workdir = str(Path(default_workdir).expanduser().resolve())
        self._agent_locks: dict[str, asyncio.Lock] = {}

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        conversation = self._store.find_one("im_conversations", {"conversation_id": conversation_id})
        if conversation is None:
            raise KeyError(f"对话不存在: {conversation_id}")
        return conversation

    def list_conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        self.get_conversation(conversation_id)
        return self._store.find_many(
            "im_messages",
            {"conversation_id": conversation_id},
            sort=[("created_at", 1)],
        )

    def list_agent_conversations(self, agent_id: str) -> list[dict[str, Any]]:
        self._bridge.ensure_agent_exists(agent_id)
        conversations: list[dict[str, Any]] = []
        records = self._store.find_many(
            "im_conversations",
            {"agent_id": agent_id},
            sort=[("updated_at", -1)],
        )
        for conversation in records:
            messages = self._store.find_many(
                "im_messages",
                {"conversation_id": conversation["conversation_id"]},
                sort=[("created_at", -1)],
                limit=1,
            )
            last_message = messages[0] if messages else None
            conversations.append(
                {
                    **conversation,
                    "agent_id": agent_id,
                    "last_message": last_message,
                    "message_count": len(self.list_conversation_messages(conversation["conversation_id"])),
                }
            )
        return conversations

    def create_agent_conversation(
        self,
        *,
        agent_id: str,
        created_by: str,
        title: str = "",
        avatar_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        agent = self._bridge.ensure_agent_exists(agent_id)
        conversation = Conversation.create(
            agent_id=agent_id,
            title=title or f"{agent.get('name', agent_id)} 对话",
            created_by=created_by,
            avatar_url=avatar_url,
            metadata={"conversation_kind": "agent_dm", **(metadata or {})},
        )
        record = self._store.insert_one("im_conversations", conversation.to_dict())
        self._events.publish(record["conversation_id"], "conversation.created", {"conversation": record})
        return record

    def add_conversation_message(
        self,
        *,
        conversation_id: str,
        sender_type: str,
        sender_id: str,
        content_parts: list[dict[str, Any]],
        reply_to: str = "",
        quote_of: str = "",
        status: str = "sent",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conversation = self.get_conversation(conversation_id)
        if sender_type == "agent" and sender_id != conversation.get("agent_id"):
            raise ValueError("该 conversation 只能由绑定 agent 回复")
        parts = [ContentPart.from_dict(part) for part in content_parts]
        if not parts:
            raise ValueError("content_parts 不能为空")
        message = Message.create(
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content_parts=parts,
            reply_to=reply_to,
            quote_of=quote_of,
            status=status,
            metadata=metadata or {},
        )
        record = self._store.insert_one("im_messages", message.to_dict())
        self._store.update_one(
            "im_conversations",
            {"conversation_id": conversation_id},
            {"updated_at": record["created_at"]},
        )
        self._events.publish(conversation_id, "message.created", {"message": record})
        return record

    async def reply_to_conversation_message(
        self,
        *,
        conversation_id: str,
        message_id: str,
        auto_start: bool = True,
    ) -> dict[str, Any]:
        conversation = self.get_conversation(conversation_id)
        message = self._get_message(message_id)
        if message.get("conversation_id") != conversation_id:
            raise ValueError("message 不属于该 conversation")
        if message.get("sender_type") != "user":
            raise ValueError("只能回复 user 消息")

        agent_id = conversation.get("agent_id", "")
        self._bridge.ensure_agent_exists(agent_id)
        if not auto_start:
            self._events.publish(conversation_id, "agent.reply.pending", {"message_id": message_id, "agent_id": agent_id})
            return {"type": "dm_reply_pending", "message_id": message_id, "agent_id": agent_id}

        lock = self._agent_locks.setdefault(agent_id, asyncio.Lock())
        async with lock:
            agent = self._bridge.get_agent(agent_id)
            self._rebuild_agent_history(agent, conversation_id=conversation_id, before_message_id=message_id)
            prompt = self._message_text(message)
            await agent.start_with_history(prompt)
            final = agent.states.get("final", "") or agent.states.get("finish_reason", "")
            reply = self.add_conversation_message(
                conversation_id=conversation_id,
                sender_type="agent",
                sender_id=agent_id,
                content_parts=[{"type": "text", "text": final or "Agent 已完成回复"}],
                status="finished",
                metadata={"source": "direct_agent_reply", "reply_to": message_id},
            )
            self._store.update_one("im_messages", {"message_id": message_id}, {"status": "finished"})
            self._events.publish(
                conversation_id,
                "agent.reply.finished",
                {"message_id": message_id, "agent_id": agent_id, "reply": reply},
            )
            return {"type": "dm_reply", "message": reply}

    def _get_message(self, message_id: str) -> dict[str, Any]:
        message = self._store.find_one("im_messages", {"message_id": message_id})
        if message is None:
            raise KeyError(f"消息不存在: {message_id}")
        return message

    def _rebuild_agent_history(self, agent, *, conversation_id: str, before_message_id: str) -> None:
        memory = agent.context_engine.get_memory()
        memory.clear_field("tool_respond")
        memory.clear_field("agent_history")
        for history_message in self._conversation_history_before(conversation_id, before_message_id):
            memory.store("agent_history", "dialogue", self._format_history_message(history_message))

    def _conversation_history_before(self, conversation_id: str, message_id: str) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for message in self.list_conversation_messages(conversation_id):
            if message.get("message_id") == message_id:
                break
            if message.get("sender_type") in {"user", "agent"}:
                history.append(message)
        return history

    def _format_history_message(self, message: dict[str, Any]) -> str:
        role = "用户" if message.get("sender_type") == "user" else "Agent"
        return f"### 历史消息\n{role}：{self._message_text(message)}"

    def _message_text(self, message: dict[str, Any]) -> str:
        parts = [ContentPart.from_dict(part) for part in message.get("content_parts", [])]
        return Message(
            message_id=message["message_id"],
            room_id=message.get("room_id", ""),
            conversation_id=message.get("conversation_id", ""),
            sender_type=message["sender_type"],
            sender_id=message["sender_id"],
            content_parts=parts,
        ).text_content()
