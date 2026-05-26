from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from im_backend.application.event_stream import RoomEventStreamService
from im_backend.domain.models import (
    AgentRuntimeProfile,
    ContentPart,
    Message,
    MessageAction,
    Room,
)
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge
from im_backend.infra.coding_agents.runners import runner_for_kind


class IMService:
    def __init__(
        self,
        *,
        store,
        bridge: AgentFlowBridge,
        room_events: RoomEventStreamService,
        default_workdir: str | Path,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = room_events
        self._default_workdir = str(Path(default_workdir).expanduser().resolve())
        self._tasks: dict[str, asyncio.Task] = {}

    def create_room(
        self,
        *,
        type: str,
        title: str = "",
        member_agent_ids: list[str] | None = None,
        created_by: str = "user",
        avatar_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        member_agent_ids = member_agent_ids or []
        if type not in {"dm", "group"}:
            raise ValueError("room type 必须是 dm 或 group")
        if type == "dm" and len(member_agent_ids) != 1:
            raise ValueError("dm 房间必须包含且只包含一个 agent")
        for agent_id in member_agent_ids:
            self._bridge.ensure_agent_exists(agent_id)

        room = Room.create(
            type=type,
            title=title,
            member_agent_ids=member_agent_ids,
            created_by=created_by,
            avatar_url=avatar_url,
            metadata=metadata or {},
        )
        record = self._store.insert_one("im_rooms", room.to_dict())
        self._events.publish(record["room_id"], "room.created", {"room": record})
        return record

    def list_rooms(self) -> list[dict[str, Any]]:
        return self._store.find_many("im_rooms", sort=[("created_at", -1)])

    def get_room(self, room_id: str) -> dict[str, Any]:
        room = self._store.find_one("im_rooms", {"room_id": room_id})
        if room is None:
            raise KeyError(f"房间不存在: {room_id}")
        return room

    def list_messages(self, room_id: str) -> list[dict[str, Any]]:
        self.get_room(room_id)
        return self._store.find_many(
            "im_messages",
            {"room_id": room_id},
            sort=[("created_at", 1)],
        )

    def list_agent_messages(self, agent_id: str) -> list[dict[str, Any]]:
        self._bridge.ensure_agent_exists(agent_id)
        rooms = self._store.find_many("im_rooms")
        room_ids = {
            room.get("room_id")
            for room in rooms
            if agent_id in (room.get("member_agent_ids") or [])
        }
        messages = [
            message
            for message in self._store.find_many("im_messages", sort=[("created_at", -1)])
            if message.get("room_id") in room_ids
            or message.get("sender_id") == agent_id
            or agent_id in (message.get("mentions") or [])
        ]
        return messages[:50]

    def list_room_tasks(self, room_id: str) -> list[dict[str, Any]]:
        self.get_room(room_id)
        tasks: list[dict[str, Any]] = []
        for message in self.list_messages(room_id):
            run_id = message.get("run_id")
            if not run_id:
                continue
            run = self._store.find_one("runs", {"run_id": run_id}) or {}
            tasks.append(
                {
                    "task_id": run_id,
                    "run_id": run_id,
                    "message_id": message.get("message_id"),
                    "prompt": run.get("prompt") or self._message_text(message),
                    "mode": run.get("mode") or message.get("metadata", {}).get("mode", ""),
                    "status": run.get("status") or message.get("status", ""),
                    "plan": run.get("plan", {}),
                    "final": run.get("final", ""),
                    "created_at": message.get("created_at"),
                    "updated_at": run.get("updated_at") or message.get("updated_at"),
                }
            )
        return sorted(tasks, key=lambda item: item.get("created_at") or 0, reverse=True)

    def get_message(self, message_id: str) -> dict[str, Any]:
        message = self._store.find_one("im_messages", {"message_id": message_id})
        if message is None:
            raise KeyError(f"消息不存在: {message_id}")
        return message

    def add_message(
        self,
        *,
        room_id: str,
        sender_type: str,
        sender_id: str,
        content_parts: list[dict[str, Any]],
        mentions: list[str] | None = None,
        reply_to: str = "",
        quote_of: str = "",
        run_id: str = "",
        status: str = "sent",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        room = self.get_room(room_id)
        parts = [ContentPart.from_dict(part) for part in content_parts]
        if not parts:
            raise ValueError("content_parts 不能为空")
        for agent_id in mentions or []:
            if agent_id not in room.get("member_agent_ids", []):
                raise ValueError(f"被 @ 的 agent 不在房间中: {agent_id}")

        message = Message.create(
            room_id=room_id,
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
        self._events.publish(room_id, "message.created", {"message": record})
        return record

    async def dispatch_message(
        self,
        *,
        room_id: str,
        message_id: str,
        planner_agent_id: str = "default_planner",
        context_id: str = "default_step",
        max_replan_rounds: int = 3,
        auto_start: bool = True,
        approved: bool = False,
    ) -> dict[str, Any]:
        room = self.get_room(room_id)
        message = self.get_message(message_id)
        if message.get("room_id") != room_id:
            raise ValueError("message 不属于该 room")
        if message.get("sender_type") != "user":
            raise ValueError("只能派发 user 消息")

        prompt = self._message_text(message)
        has_mentions = bool(message.get("mentions"))
        target_agent_ids = self._select_target_agents(room, message)
        profiles = [self._runtime_profile(agent_id) for agent_id in target_agent_ids]
        external_profiles = [profile for profile in profiles if profile.agent_kind in {"claude_code", "codex"}]

        if external_profiles and not approved:
            return self._create_confirmation(
                room_id=room_id,
                message_id=message_id,
                profiles=external_profiles,
                prompt=prompt,
            )

        if len(target_agent_ids) == 1 and (room.get("type") == "dm" or has_mentions):
            profile = profiles[0]
            if profile.agent_kind in {"claude_code", "codex"}:
                return await self._dispatch_coding_agent(
                    room_id=room_id,
                    message_id=message_id,
                    prompt=prompt,
                    profile=profile,
                )
            run = self._create_agent_flow_run(
                room=room,
                message=message,
                prompt=prompt,
                mode="react",
                executor_agent_id=profile.agent_id,
                auto_start=auto_start,
            )
            return self._mark_dispatched(room_id, message_id, run)

        native_agent_ids = [
            profile.agent_id
            for profile in profiles
            if profile.agent_kind in {"native", "human_proxy"}
        ]
        if not native_agent_ids:
            raise ValueError("没有可由 PlanOrchestrator 调度的 native executor")
        run = self._create_agent_flow_run(
            room=room,
            message=message,
            prompt=prompt,
            mode="plan",
            planner_agent_id=planner_agent_id,
            executor_agent_ids=native_agent_ids,
            context_id=context_id,
            max_replan_rounds=max_replan_rounds,
            auto_start=auto_start,
        )
        return self._mark_dispatched(room_id, message_id, run)

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
        self._events.publish(
            message["room_id"],
            "message.action",
            {"message_id": message_id, "action": record},
        )
        return record

    def _select_target_agents(self, room: dict[str, Any], message: dict[str, Any]) -> list[str]:
        mentions = [
            agent_id
            for agent_id in message.get("mentions", [])
            if agent_id in room.get("member_agent_ids", [])
        ]
        if mentions:
            return mentions
        members = room.get("member_agent_ids", [])
        if room.get("type") == "dm":
            return members[:1]
        return members

    def _runtime_profile(self, agent_id: str) -> AgentRuntimeProfile:
        record = self._bridge.ensure_agent_exists(agent_id)
        profile = AgentRuntimeProfile.from_agent_record(record)
        if not profile.workdir:
            profile.workdir = self._default_workdir
        return profile

    def _message_text(self, message: dict[str, Any]) -> str:
        parts = [ContentPart.from_dict(part) for part in message.get("content_parts", [])]
        return Message(
            message_id=message["message_id"],
            room_id=message["room_id"],
            sender_type=message["sender_type"],
            sender_id=message["sender_id"],
            content_parts=parts,
        ).text_content()

    def _create_agent_flow_run(
        self,
        *,
        room: dict[str, Any],
        message: dict[str, Any],
        prompt: str,
        mode: str,
        executor_agent_id: str | None = None,
        planner_agent_id: str = "default_planner",
        executor_agent_ids: list[str] | None = None,
        context_id: str = "default_step",
        max_replan_rounds: int = 3,
        auto_start: bool = True,
    ) -> dict[str, Any]:
        runtime_conversation = self._bridge.create_runtime_conversation(
            title=f"IM:{room.get('title', room['room_id'])}",
            metadata={"source": "im_backend", "room_id": room["room_id"]},
        )
        runtime_message = self._bridge.add_runtime_message(
            conversation_id=runtime_conversation["conversation_id"],
            role="user",
            content=prompt,
            metadata={"source": "im_backend", "room_id": room["room_id"], "message_id": message["message_id"]},
        )
        return self._bridge.create_run(
            prompt=prompt,
            mode=mode,
            executor_agent_id=executor_agent_id,
            planner_agent_id=planner_agent_id,
            executor_agent_ids=executor_agent_ids or ([] if executor_agent_id is None else [executor_agent_id]),
            context_id=context_id,
            max_replan_rounds=max_replan_rounds,
            conversation_id=runtime_conversation["conversation_id"],
            message_id=runtime_message["message_id"],
            auto_start=auto_start,
        )

    def _mark_dispatched(self, room_id: str, message_id: str, run: dict[str, Any]) -> dict[str, Any]:
        self._store.update_one(
            "im_messages",
            {"message_id": message_id},
            {"run_id": run["run_id"], "status": "running" if run.get("status") == "running" else "sent"},
        )
        self._events.publish(room_id, "run.created", {"message_id": message_id, "run": run})
        return {"type": "run", "run": run}

    def _create_confirmation(
        self,
        *,
        room_id: str,
        message_id: str,
        profiles: list[AgentRuntimeProfile],
        prompt: str,
    ) -> dict[str, Any]:
        payload = {
            "message_id": message_id,
            "agent_ids": [profile.agent_id for profile in profiles],
            "agent_kinds": [profile.agent_kind for profile in profiles],
            "prompt": prompt,
            "reason": "外部 coding agent 执行前需要人工确认",
        }
        confirmation = self.add_message(
            room_id=room_id,
            sender_type="system",
            sender_id="im_backend",
            content_parts=[
                {
                    "type": "deploy",
                    "title": "需要确认外部 Agent 执行",
                    "description": "Claude Code / Codex 可能读取项目并生成修改建议，v1 默认需要人工确认。",
                    "metadata": payload,
                }
            ],
            status="pending",
            metadata={"confirmation": payload},
        )
        self._events.publish(room_id, "confirmation.requested", {"confirmation": confirmation, **payload})
        return {"type": "confirmation", "confirmation": confirmation}

    async def _dispatch_coding_agent(
        self,
        *,
        room_id: str,
        message_id: str,
        prompt: str,
        profile: AgentRuntimeProfile,
    ) -> dict[str, Any]:
        runner = runner_for_kind(profile.agent_kind)
        if runner is None:
            raise ValueError(f"不支持的 coding agent: {profile.agent_kind}")
        run_id = f"coding-{message_id}"
        self._store.update_one(
            "im_messages",
            {"message_id": message_id},
            {"run_id": run_id, "status": "running"},
        )
        task = asyncio.create_task(
            self._run_coding_agent_task(
                room_id=room_id,
                message_id=message_id,
                run_id=run_id,
                profile=profile,
                prompt=prompt,
            )
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task, rid=run_id: self._tasks.pop(rid, None))
        self._events.publish(
            room_id,
            "run.created",
            {
                "message_id": message_id,
                "run": {
                    "run_id": run_id,
                    "mode": "coding_agent",
                    "executor_agent_id": profile.agent_id,
                    "status": "running",
                },
            },
        )
        return {"type": "coding_agent_run", "run_id": run_id, "agent_id": profile.agent_id}

    async def _run_coding_agent_task(
        self,
        *,
        room_id: str,
        message_id: str,
        run_id: str,
        profile: AgentRuntimeProfile,
        prompt: str,
    ) -> None:
        runner = runner_for_kind(profile.agent_kind)
        if runner is None:
            return
        final_chunks: list[str] = []
        try:
            async for event in runner.run(prompt=prompt, workdir=profile.workdir):
                payload = {
                    "run_id": run_id,
                    "agent_id": profile.agent_id,
                    "agent_kind": profile.agent_kind,
                    **event.payload,
                }
                if event.type == "agent.delta":
                    final_chunks.append(payload.get("delta", ""))
                if event.type == "agent.final" and payload.get("final"):
                    final_chunks.append(payload["final"])
                self._events.publish(room_id, event.type, payload)
            final = "".join(final_chunks).strip()
            self.add_message(
                room_id=room_id,
                sender_type="agent",
                sender_id=profile.agent_id,
                content_parts=[{"type": "text", "text": final or "Coding agent 执行完成"}],
                run_id=run_id,
                status="finished",
                metadata={"agent_kind": profile.agent_kind},
            )
            self._store.update_one("im_messages", {"message_id": message_id}, {"status": "finished"})
            self._events.publish(room_id, "workflow.finished", {"run_id": run_id, "final": final})
        except Exception as exc:
            self._store.update_one("im_messages", {"message_id": message_id}, {"status": "failed"})
            self._events.publish(room_id, "agent.failed", {"run_id": run_id, "error": str(exc)})


class AgentCatalogService:
    def __init__(self, bridge: AgentFlowBridge) -> None:
        self._bridge = bridge

    def list_agents(self) -> list[dict[str, Any]]:
        return self._bridge.list_agents()
