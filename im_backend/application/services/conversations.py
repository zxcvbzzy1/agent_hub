from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from im_backend.application.services.agents import IMAgentService
from im_backend.application.services.cleanup import IMCleanupService
from im_backend.application.services.coding_agents import CodingAgentService
from im_backend.application.services.events import RoomEventStreamService
from im_backend.domain.models import AgentRuntimeProfile, ContentPart, Conversation, Message
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class ConversationService:
    """Single-agent conversation use cases."""

    def __init__(
        self,
        *,
        store,
        bridge: AgentFlowBridge,
        events: RoomEventStreamService,
        default_workdir: str | Path,
        agents: IMAgentService,
        coding_agents: CodingAgentService,
        cleanup: IMCleanupService | None = None,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = events
        self._agents = agents
        self._coding_agents = coding_agents
        self._default_workdir = str(Path(default_workdir).expanduser().resolve())
        self._agent_locks: dict[str, asyncio.Lock] = {}
        self._reply_tasks: dict[str, asyncio.Task] = {}
        self._cleanup = cleanup or IMCleanupService(store)

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
        agent = self._agents.ensure_agent_access(agent_id, created_by)
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

    def delete_conversation(self, conversation_id: str) -> dict[str, Any]:
        self.get_conversation(conversation_id)
        stats = self._cleanup.delete_conversation(conversation_id)
        return {"deleted": True, "conversation_id": conversation_id, "stats": stats}

    def add_conversation_message(
        self,
        *,
        conversation_id: str,
        sender_type: str,
        sender_id: str,
        content_parts: list[dict[str, Any]],
        reply_to: str = "",
        quote_of: str = "",
        run_id: str = "",
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
            run_id=run_id,
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
        profile = self._runtime_profile(agent_id)
        if not auto_start:
            self._events.publish(conversation_id, "agent.reply.pending", {"message_id": message_id, "agent_id": agent_id})
            return {"type": "dm_reply_pending", "message_id": message_id, "agent_id": agent_id}

        if message.get("status") == "running":
            return {"type": "dm_reply_started", "message_id": message_id, "agent_id": agent_id}
        self._store.update_one("im_messages", {"message_id": message_id}, {"status": "running"})
        self._events.publish(
            conversation_id,
            "agent.reply.started",
            {"message_id": message_id, "agent_id": agent_id, "conversation_id": conversation_id},
        )
        if profile.agent_kind in {"claude_code", "codex"}:
            run_id = f"coding-{message_id}-{agent_id}"
            self._store.update_one("im_messages", {"message_id": message_id}, {"run_id": run_id})
            result, task = self._coding_agents.start_coding_agent(
                scope_id=conversation_id,
                message_id=message_id,
                run_id=run_id,
                prompt=self._message_text(message),
                profile=profile,
                mode="direct_coding_agent",
                final_message_writer=lambda final: self.add_conversation_message(
                    conversation_id=conversation_id,
                    sender_type="agent",
                    sender_id=agent_id,
                    content_parts=[{"type": "text", "text": final or "Coding agent 已完成回复"}],
                    run_id=run_id,
                    status="finished",
                    metadata={
                        "source": "direct_coding_agent_reply",
                        "reply_to": message_id,
                        "agent_kind": profile.agent_kind,
                    },
                ),
            )
            self._reply_tasks[message_id] = task
            task.add_done_callback(lambda _task, mid=message_id: self._reply_tasks.pop(mid, None))
            return {"type": "dm_reply_started", "message_id": message_id, "agent_id": agent_id, "run": result}

        task = asyncio.create_task(
            self._run_reply_task(
                conversation_id=conversation_id,
                message_id=message_id,
                agent_id=agent_id,
            )
        )
        self._reply_tasks[message_id] = task
        task.add_done_callback(lambda _task, mid=message_id: self._reply_tasks.pop(mid, None))
        return {"type": "dm_reply_started", "message_id": message_id, "agent_id": agent_id}

    def _runtime_profile(self, agent_id: str) -> AgentRuntimeProfile:
        record = self._bridge.ensure_agent_exists(agent_id)
        profile = AgentRuntimeProfile.from_agent_record(record)
        if not profile.workdir:
            profile.workdir = self._default_workdir
        return profile

    async def cancel_conversation_reply(self, *, conversation_id: str, message_id: str) -> dict[str, Any]:
        conversation = self.get_conversation(conversation_id)
        message = self._get_message(message_id)
        if message.get("conversation_id") != conversation_id:
            raise ValueError("message 不属于该 conversation")
        if message.get("sender_type") != "user":
            raise ValueError("只能中断 user 消息触发的回复")
        if message.get("status") == "cancelled":
            return {
                "type": "dm_reply_cancelled",
                "conversation_id": conversation_id,
                "message_id": message_id,
                "cancelled": True,
            }
        if message.get("status") != "running":
            raise ValueError("该消息没有正在运行的回复")

        task = self._reply_tasks.get(message_id)
        if task and not task.done():
            task.cancel()
        self._mark_reply_cancelled(
            conversation_id=conversation_id,
            message_id=message_id,
            agent_id=conversation.get("agent_id", ""),
            publish=True,
        )
        return {
            "type": "dm_reply_cancelled",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "cancelled": True,
        }

    async def _run_reply_task(self, *, conversation_id: str, message_id: str, agent_id: str) -> None:
        lock = self._agent_locks.setdefault(agent_id, asyncio.Lock())
        registered = False
        async with lock:
            agent = self._bridge.get_agent(agent_id)
            message = self._get_message(message_id)
            if message.get("status") == "cancelled":
                return
            self._rebuild_agent_history(agent, conversation_id=conversation_id, before_message_id=message_id)
            prompt = self._message_text(message)
            self._bridge.register_agent_runtime_scope(agent_id, conversation_id)
            registered = True
            self._events.publish(
                conversation_id,
                "workflow.started",
                {
                    "scope_id": conversation_id,
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "agent_id": agent_id,
                    "mode": "direct",
                    "prompt": prompt,
                },
            )
            try:
                await agent.start_with_history(prompt)
                if self._get_message(message_id).get("status") == "cancelled":
                    return
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
                self._events.publish(
                    conversation_id,
                    "workflow.finished",
                    {
                        "scope_id": conversation_id,
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                        "agent_id": agent_id,
                        "mode": "direct",
                        "final": final,
                    },
                )
                return
            except asyncio.CancelledError:
                current = self._get_message(message_id)
                self._mark_reply_cancelled(
                    conversation_id=conversation_id,
                    message_id=message_id,
                    agent_id=agent_id,
                    publish=current.get("status") != "cancelled",
                )
                raise
            except Exception as exc:
                self._store.update_one("im_messages", {"message_id": message_id}, {"status": "failed"})
                self._events.publish(
                    conversation_id,
                    "workflow.failed",
                    {
                        "scope_id": conversation_id,
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                        "agent_id": agent_id,
                        "mode": "direct",
                        "error": str(exc),
                    },
                )
                raise
            finally:
                if registered:
                    self._bridge.unregister_agent_runtime_scope(agent_id, conversation_id)

    def _mark_reply_cancelled(
        self,
        *,
        conversation_id: str,
        message_id: str,
        agent_id: str,
        publish: bool,
    ) -> None:
        self._store.update_one("im_messages", {"message_id": message_id}, {"status": "cancelled"})
        if publish:
            self._events.publish(
                conversation_id,
                "workflow.failed",
                {
                    "scope_id": conversation_id,
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "agent_id": agent_id,
                    "mode": "direct",
                    "error": "用户中断",
                    "cancelled": True,
                },
            )

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
