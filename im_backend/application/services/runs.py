from __future__ import annotations

from pathlib import Path
from typing import Any

from im_backend.application.services.agents import IMAgentService
from im_backend.application.services.coding_agents import CodingAgentService
from im_backend.application.services.events import RoomEventStreamService
from im_backend.application.services.messages import GroupMessageService
from im_backend.application.services.rooms import RoomService
from im_backend.domain.models import AgentRuntimeProfile
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class GroupRunService:
    def __init__(
        self,
        *,
        store,
        bridge: AgentFlowBridge,
        events: RoomEventStreamService,
        rooms: RoomService,
        messages: GroupMessageService,
        coding_agents: CodingAgentService,
        agents: IMAgentService,
        default_workdir: str | Path,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._events = events
        self._rooms = rooms
        self._messages = messages
        self._coding_agents = coding_agents
        self._agents = agents
        self._default_workdir = str(Path(default_workdir).expanduser().resolve())

    def list_room_tasks(self, room_id: str) -> list[dict[str, Any]]:
        room = self._rooms.ensure_group_room(room_id)
        if room.get("type") != "group":
            raise ValueError("只有群聊 room 才有编排任务")
        tasks: list[dict[str, Any]] = []
        for message in self._messages.list_messages(room_id):
            run_id = message.get("run_id")
            if not run_id:
                continue
            run = self._store.find_one("runs", {"run_id": run_id}) or {}
            tasks.append(
                {
                    "task_id": run_id,
                    "run_id": run_id,
                    "message_id": message.get("message_id"),
                    "prompt": run.get("prompt") or self._messages.message_text(message),
                    "mode": run.get("mode") or message.get("metadata", {}).get("mode", ""),
                    "status": run.get("status") or message.get("status", ""),
                    "plan": run.get("plan", {}),
                    "final": run.get("final", ""),
                    "created_at": message.get("created_at"),
                    "updated_at": run.get("updated_at") or message.get("updated_at"),
                }
            )
        return sorted(tasks, key=lambda item: item.get("created_at") or 0, reverse=True)

    def list_room_run_ids(self, room_id: str) -> list[str]:
        return [
            message.get("run_id", "")
            for message in self._messages.list_messages(room_id)
            if message.get("run_id")
        ]

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
        user_id: str = "",
    ) -> dict[str, Any]:
        room = self._rooms.ensure_group_room(room_id)
        message = self._messages.get_message(message_id)
        if message.get("room_id") != room_id:
            raise ValueError("message 不属于该 room")
        if message.get("sender_type") != "user":
            raise ValueError("只能派发 user 消息")

        prompt = self._messages.message_text(message)
        target_agent_ids = self._select_target_agents(room, message)
        profiles = [self._runtime_profile(agent_id, user_id=user_id) for agent_id in target_agent_ids]
        external_profiles = [profile for profile in profiles if profile.agent_kind in {"claude_code", "codex"}]

        if external_profiles and not approved:
            return self._create_confirmation(
                room_id=room_id,
                message_id=message_id,
                profiles=external_profiles,
                prompt=prompt,
            )

        native_agent_ids = [
            profile.agent_id
            for profile in profiles
            if profile.agent_kind in {"native", "human_proxy"}
        ]
        external_runs: list[dict[str, str]] = []
        if approved:
            for profile in external_profiles:
                external_runs.append(
                    await self._coding_agents.dispatch_coding_agent(
                        room_id=room_id,
                        message_id=message_id,
                        prompt=prompt,
                        profile=profile,
                    )
                )
            if external_runs:
                current_message = self._messages.get_message(message_id)
                self._store.update_one(
                    "im_messages",
                    {"message_id": message_id},
                    {
                        "metadata": {
                            **(current_message.get("metadata") or {}),
                            "external_run_ids": [item["run_id"] for item in external_runs],
                        }
                    },
                )

        native_run = None
        if native_agent_ids:
            native_run = self._create_agent_flow_run(
                room=room,
                message=message,
                prompt=prompt,
                mode="plan",
                planner_agent_id=room.get("metadata", {}).get("planner_agent_id") or planner_agent_id,
                executor_agent_ids=native_agent_ids,
                context_id=context_id,
                max_replan_rounds=max_replan_rounds,
                auto_start=auto_start,
                user_id=user_id,
            )
            self._mark_dispatched(room_id, message_id, native_run)

        if not native_run and not external_runs:
            raise ValueError("没有可调度的 executor")
        return {
            "type": "mixed_run" if native_run and external_runs else ("run" if native_run else "coding_agent_runs"),
            "run": native_run,
            "external_runs": external_runs,
        }

    def cancel_room_run(self, *, room_id: str, run_id: str, actor_id: str = "user") -> dict[str, Any]:
        self._rooms.ensure_group_room(room_id)
        messages = [
            message
            for message in self._messages.list_messages(room_id)
            if message.get("run_id") == run_id or run_id in (message.get("metadata", {}).get("external_run_ids") or [])
        ]
        if not messages:
            raise KeyError(f"run 不属于该 room: {run_id}")
        message_id = messages[0].get("message_id", "")
        if run_id.startswith("coding-"):
            self._coding_agents.cancel_run(run_id)
            run = {"run_id": run_id, "status": "cancelled", "mode": "coding_agent"}
        else:
            run = self._bridge.cancel_run(run_id)
        self._store.update_one(
            "im_messages",
            {"message_id": message_id},
            {"status": "cancelled"},
        )
        payload = {
            "run_id": run_id,
            "message_id": message_id,
            "room_id": room_id,
            "actor_id": actor_id,
            "cancelled": True,
            "run": run,
        }
        self._events.publish(room_id, "run.cancelled", payload)
        return {"type": "run_cancelled", **payload}

    def _select_target_agents(self, room: dict[str, Any], message: dict[str, Any]) -> list[str]:
        mentions = [
            agent_id
            for agent_id in message.get("mentions", [])
            if agent_id in room.get("member_agent_ids", [])
        ]
        if mentions:
            return mentions
        return room.get("member_agent_ids", [])

    def _runtime_profile(self, agent_id: str, *, user_id: str = "") -> AgentRuntimeProfile:
        record = self._agents.ensure_agent_access(agent_id, user_id) if user_id else self._bridge.ensure_agent_exists(agent_id)
        profile = AgentRuntimeProfile.from_agent_record(record)
        if not profile.workdir:
            profile.workdir = self._default_workdir
        return profile

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
        user_id: str = "",
    ) -> dict[str, Any]:
        if user_id:
            self._agents.ensure_agent_access(planner_agent_id, user_id)
            self._agents.ensure_context_access(context_id, user_id)
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
        confirmation = self._messages.add_message(
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
