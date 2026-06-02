from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from im_backend.application.services.platform.events import RoomEventStreamService
from im_backend.application.services.messaging.messages import GroupMessageService
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
        run_id = f"coding-{message_id}-{profile.agent_id}"
        self._store.update_one(
            "im_messages",
            {"message_id": message_id},
            {"run_id": run_id, "status": "running"},
        )
        result, _task = self.start_coding_agent(
            scope_id=room_id,
            message_id=message_id,
            run_id=run_id,
            prompt=prompt,
            profile=profile,
            mode="coding_agent",
            final_message_writer=lambda final: self._messages.add_message(
                room_id=room_id,
                sender_type="agent",
                sender_id=profile.agent_id,
                content_parts=[{"type": "text", "text": final or "Coding agent 执行完成"}],
                run_id=run_id,
                status="finished",
                metadata={"agent_kind": profile.agent_kind},
            ),
        )
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
        return result

    def start_coding_agent(
        self,
        *,
        scope_id: str,
        message_id: str,
        run_id: str,
        prompt: str,
        profile: AgentRuntimeProfile,
        mode: str,
        final_message_writer: Callable[[str], dict[str, Any]],
    ) -> tuple[dict[str, str], asyncio.Task]:
        if runner_for_kind(profile.agent_kind) is None:
            raise ValueError(f"不支持的 coding agent: {profile.agent_kind}")
        self._store.update_one(
            "im_messages",
            {"message_id": message_id},
            {"status": "running"},
        )
        task = asyncio.create_task(
            self._run_coding_agent_task(
                scope_id=scope_id,
                message_id=message_id,
                run_id=run_id,
                profile=profile,
                prompt=prompt,
                mode=mode,
                final_message_writer=final_message_writer,
            )
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task, rid=run_id: self._tasks.pop(rid, None))
        self._events.publish(
            scope_id,
            "workflow.started",
            {
                "message_id": message_id,
                "run_id": run_id,
                "scope_id": scope_id,
                "agent_id": profile.agent_id,
                "agent_kind": profile.agent_kind,
                "mode": mode,
                "prompt": prompt,
            },
        )
        return {"type": "coding_agent_run", "run_id": run_id, "agent_id": profile.agent_id}, task

    def cancel_run(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if not task or task.done():
            return False
        task.cancel()
        return True

    async def _run_coding_agent_task(
        self,
        *,
        scope_id: str,
        message_id: str,
        run_id: str,
        profile: AgentRuntimeProfile,
        prompt: str,
        mode: str,
        final_message_writer: Callable[[str], dict[str, Any]],
    ) -> None:
        runner = runner_for_kind(profile.agent_kind)
        if runner is None:
            return
        final_chunks: list[str] = []
        emitted_final = False
        try:
            async for event in runner.run(
                prompt=prompt,
                workdir=profile.workdir,
                permission_profile=profile.permission_profile,
            ):
                payload = {
                    "run_id": run_id,
                    "agent_id": profile.agent_id,
                    "agent_kind": profile.agent_kind,
                    "scope_id": scope_id,
                    "message_id": message_id,
                    "mode": mode,
                    **event.payload,
                }
                if event.type == "agent.delta":
                    final_chunks.append(payload.get("delta", ""))
                    # 高频流式增量不落库、不做订阅者扇出，避免逐 chunk 同步 insert_one 阻塞事件循环
                    # 并在前端造成卡死/重连重放；最终文本由下面的 agent.final + 落库消息承载。
                    self._events.no_store_publish(scope_id, event.type, payload)
                    continue
                if event.type == "agent.final" and payload.get("final"):
                    final_chunks.append(payload["final"])
                    emitted_final = True
                self._events.publish(scope_id, event.type, payload)
            final = "".join(final_chunks).strip()
            reply = final_message_writer(final)
            self._store.update_one("im_messages", {"message_id": message_id}, {"status": "finished"})
            if not emitted_final:
                self._events.publish(
                    scope_id,
                    "agent.final",
                    {
                        "run_id": run_id,
                        "scope_id": scope_id,
                        "message_id": message_id,
                        "agent_id": profile.agent_id,
                        "agent_kind": profile.agent_kind,
                        "mode": mode,
                        "final": final,
                    },
                )
            self._events.publish(
                scope_id,
                "agent.reply.finished",
                {"message_id": message_id, "agent_id": profile.agent_id, "reply": reply},
            )
            self._events.publish(
                scope_id,
                "workflow.finished",
                {
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "message_id": message_id,
                    "agent_id": profile.agent_id,
                    "agent_kind": profile.agent_kind,
                    "mode": mode,
                    "final": final,
                },
            )
        except asyncio.CancelledError:
            current = self._store.find_one("im_messages", {"message_id": message_id}) or {}
            self._store.update_one("im_messages", {"message_id": message_id}, {"status": "cancelled"})
            if current.get("status") != "cancelled":
                self._events.publish(
                    scope_id,
                    "workflow.failed",
                    {
                        "run_id": run_id,
                        "scope_id": scope_id,
                        "message_id": message_id,
                        "agent_id": profile.agent_id,
                        "agent_kind": profile.agent_kind,
                        "mode": mode,
                        "error": "用户中断",
                        "cancelled": True,
                    },
                )
            raise
        except Exception as exc:
            self._store.update_one("im_messages", {"message_id": message_id}, {"status": "failed"})
            self._events.publish(
                scope_id,
                "agent.failed",
                {
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "message_id": message_id,
                    "agent_id": profile.agent_id,
                    "agent_kind": profile.agent_kind,
                    "mode": mode,
                    "error": str(exc),
                },
            )
            self._events.publish(
                scope_id,
                "workflow.failed",
                {
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "message_id": message_id,
                    "agent_id": profile.agent_id,
                    "agent_kind": profile.agent_kind,
                    "mode": mode,
                    "error": str(exc),
                },
            )
