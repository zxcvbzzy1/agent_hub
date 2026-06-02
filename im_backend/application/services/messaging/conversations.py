from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from im_backend.application.services.messaging.agents import IMAgentService
from im_backend.application.services.platform.cleanup import IMCleanupService
from im_backend.application.services.orchestration.coding_agents import CodingAgentService
from im_backend.application.services.platform.events import RoomEventStreamService
from im_backend.application.services.messaging.favorites import FavoriteService
from im_backend.application.services._shared.history import history_before
from im_backend.application.services._shared.lookup import find_im_message, require_im_message
from im_backend.application.services._shared.message_text import message_text
from im_backend.application.services._shared.runtime_profile import build_runtime_profile
from im_backend.application.services._shared.inline_artifacts import collect_inline_artifact_parts
from im_backend.application.services._shared.prompting import compose_prompt_with_references
from im_backend.domain.models import AgentRuntimeProfile, ContentPart, Conversation, Message, now_ts
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
        favorites: FavoriteService,
        cleanup: IMCleanupService | None = None,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = events
        self._agents = agents
        self._coding_agents = coding_agents
        self._favorites = favorites
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

    def list_agent_conversations(self, agent_id: str, user_id: str = "") -> list[dict[str, Any]]:
        if user_id:
            self._agents.ensure_agent_access(agent_id, user_id)
        else:
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
                    "pinned": bool(conversation.get("pinned", False)),
                    "archived": bool(conversation.get("archived", False)),
                    "last_message": last_message,
                    "message_count": len(self.list_conversation_messages(conversation["conversation_id"])),
                }
            )
        # store 已按 updated_at 倒序；这里稳定排序把置顶提到最前，组内顺序不变。
        conversations.sort(key=lambda item: not item.get("pinned", False))
        return conversations

    def update_conversation(
        self,
        conversation_id: str,
        *,
        pinned: bool | None = None,
        archived: bool | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        self.get_conversation(conversation_id)
        updates: dict[str, Any] = {}
        timestamp = now_ts()
        if title is not None:
            cleaned = title.strip()
            if cleaned:
                updates["title"] = cleaned
        if pinned is not None:
            updates["pinned"] = bool(pinned)
            updates["pinned_at"] = timestamp if pinned else 0.0
        if archived is not None:
            updates["archived"] = bool(archived)
            updates["archived_at"] = timestamp if archived else 0.0
            # 归档时自动取消置顶。
            if archived and pinned is None:
                updates["pinned"] = False
                updates["pinned_at"] = 0.0
        if not updates:
            return self.get_conversation(conversation_id)
        record = self._store.update_one("im_conversations", {"conversation_id": conversation_id}, updates)
        record = record or self.get_conversation(conversation_id)
        self._events.publish(conversation_id, "conversation.updated", {"conversation": record})
        return record

    async def regenerate_reply(
        self,
        *,
        conversation_id: str,
        message_id: str,
        auto_start: bool = True,
    ) -> dict[str, Any]:
        self.get_conversation(conversation_id)
        message = self._get_message(message_id)
        if message.get("conversation_id") != conversation_id:
            raise ValueError("message 不属于该 conversation")
        if message.get("sender_type") != "user":
            raise ValueError("只能对用户消息重新生成回复")

        # 取消可能仍在运行的旧回复任务，并等它完全结算（状态写回 cancelled、回调 pop）后再继续，
        # 否则被取消的旧任务会在新任务注册后才把用户消息改回 cancelled，并把新任务从 _reply_tasks 中 pop 掉。
        task = self._reply_tasks.get(message_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        # 删除上一轮该用户消息触发的 agent 回复（含同条消息内的内联产物）。
        removed = 0
        for reply in self.list_conversation_messages(conversation_id):
            if reply.get("sender_type") != "agent":
                continue
            if (reply.get("metadata") or {}).get("reply_to") == message_id:
                self._cleanup.delete_message(reply)
                removed += 1

        # 重置用户消息状态并重新触发回复。
        self._store.update_one("im_messages", {"message_id": message_id}, {"status": "sent", "run_id": ""})
        self._events.publish(
            conversation_id,
            "message.regenerated",
            {"message_id": message_id, "removed": removed},
        )
        result = await self.reply_to_conversation_message(
            conversation_id=conversation_id,
            message_id=message_id,
            auto_start=auto_start,
        )
        return {"type": "dm_regenerated", "message_id": message_id, "removed": removed, "reply": result}

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
                prompt=self._compose_prompt_with_history(
                    conversation_id=conversation_id,
                    message=message,
                ),
                profile=profile,
                mode="direct_coding_agent",
                final_message_writer=lambda final, artifact_parts: self.add_conversation_message(
                    conversation_id=conversation_id,
                    sender_type="agent",
                    sender_id=agent_id,
                    content_parts=[
                        {"type": "text", "text": final or "Coding agent 已完成回复"},
                        *artifact_parts,
                    ],
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
            task.add_done_callback(
            lambda finished, mid=message_id: (
                self._reply_tasks.pop(mid, None) if self._reply_tasks.get(mid) is finished else None
            )
        )
            return {"type": "dm_reply_started", "message_id": message_id, "agent_id": agent_id, "run": result}

        task = asyncio.create_task(
            self._run_reply_task(
                conversation_id=conversation_id,
                message_id=message_id,
                agent_id=agent_id,
            )
        )
        self._reply_tasks[message_id] = task
        task.add_done_callback(
            lambda finished, mid=message_id: (
                self._reply_tasks.pop(mid, None) if self._reply_tasks.get(mid) is finished else None
            )
        )
        return {"type": "dm_reply_started", "message_id": message_id, "agent_id": agent_id}

    def _runtime_profile(self, agent_id: str) -> AgentRuntimeProfile:
        record = self._bridge.ensure_agent_exists(agent_id)
        return build_runtime_profile(record, default_workdir=self._default_workdir)

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
            prompt = self._compose_prompt(message)
            self._apply_native_workdir(agent, agent_id)
            self._apply_pinned_context(agent, conversation_id)
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
            started_at = time.time()
            try:
                await agent.start_with_history(prompt)
                if self._get_message(message_id).get("status") == "cancelled":
                    return
                final = agent.states.get("final", "") or agent.states.get("finish_reason", "")
                content_parts: list[dict[str, Any]] = [
                    {"type": "text", "text": final or "Agent 已完成回复"}
                ]
                content_parts.extend(
                    collect_inline_artifact_parts(
                        self._bridge.list_run_events(conversation_id),
                        since=started_at,
                        run_id=conversation_id,
                    )
                )
                reply = self.add_conversation_message(
                    conversation_id=conversation_id,
                    sender_type="agent",
                    sender_id=agent_id,
                    content_parts=content_parts,
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
        return require_im_message(self._store, message_id)

    def _apply_pinned_context(self, agent, conversation_id: str) -> None:
        """把当前会话的收藏作为固定上下文写入 agent state。"""
        states = getattr(agent, "states", None)
        if isinstance(states, dict):
            states["pinned_context"] = self._favorites.context_items("conversation", conversation_id)

    def _rebuild_agent_history(self, agent, *, conversation_id: str, before_message_id: str) -> None:
        memory = agent.context_engine.get_memory()
        memory.clear_field("tool_respond")
        memory.clear_field("agent_history")
        for history_message in self._conversation_history_before(conversation_id, before_message_id):
            memory.store("agent_history", "dialogue", self._format_history_message(history_message))

    def _conversation_history_before(self, conversation_id: str, message_id: str) -> list[dict[str, Any]]:
        return history_before(self.list_conversation_messages(conversation_id), message_id)

    def _format_history_message(self, message: dict[str, Any]) -> str:
        role = "用户" if message.get("sender_type") == "user" else "Agent"
        return f"### 历史消息\n{role}：{message_text(message)}"

    def _compose_prompt(self, message: dict[str, Any]) -> str:
        """拼接被回复/引用消息的上下文，让 agent 看到完整意图。"""
        return compose_prompt_with_references(
            message,
            lookup=lambda mid: find_im_message(self._store, mid),
            text_of=message_text,
        )

    def _compose_prompt_with_history(self, *, conversation_id: str, message: dict[str, Any]) -> str:
        """为外部 coding agent 拼接单聊历史。

        Claude Code / Codex 直通 CLI，不走 AgentBase 的 ContextEngine 记忆重建；
        因此这里把当前消息之前的对话历史显式拼进 prompt。
        """
        history = self._conversation_history_before(conversation_id, message["message_id"])
        current = self._compose_prompt(message)
        if not history:
            return current
        history_text = "\n\n".join(self._format_history_message(item) for item in history)
        return f"## 对话历史\n{history_text}\n\n## 当前消息\n{current}"

    def _apply_native_workdir(self, agent, agent_id: str) -> None:
        """把 native agent 的工作目录落到运行实例的 work_path（按 profile 取，含默认值）。"""
        profile = self._runtime_profile(agent_id)
        if profile.agent_kind not in {"native", "human_proxy"} or not profile.workdir:
            return
        if hasattr(agent, "inject_attribute"):
            agent.inject_attribute(work_path=profile.workdir)
        elif hasattr(agent, "work_path"):
            agent.work_path = profile.workdir
