from __future__ import annotations

import asyncio

from im_backend.application.services.events import RoomEventStreamService
from im_backend.application.services.messages import GroupMessageService
from im_backend.domain.models import AgentRuntimeProfile
from im_backend.infra.coding_agents.runners import runner_for_kind


class CodingAgentService:
    def __init__(
        self,
        *,
        store,
        events: RoomEventStreamService,
        messages: GroupMessageService,
    ) -> None:
        self._store = store
        self._events = events
        self._messages = messages
        self._tasks: dict[str, asyncio.Task] = {}

    async def dispatch_coding_agent(
        self,
        *,
        room_id: str,
        message_id: str,
        prompt: str,
        profile: AgentRuntimeProfile,
    ) -> dict[str, str]:
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
            self._messages.add_message(
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
