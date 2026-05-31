from __future__ import annotations

from collections.abc import Callable
from typing import Any

from im_backend.domain.models import AgentRuntimeProfile
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
from im_backend.infra.coding_agents.runners import runner_for_kind

ensure_agent_flow_path()

from application.services.events import EventStreamService  # type: ignore  # noqa: E402
from domain.agent_base import AgentBase  # type: ignore  # noqa: E402
from domain.context.context import ContextEngine  # type: ignore  # noqa: E402
from domain.context.providers import HistoryProvider, UserPromptProvider  # type: ignore  # noqa: E402
from domain.context.strategy import FullHistoryStrategy, RecencyStrategy  # type: ignore  # noqa: E402
from domain.memory.short.default_short_term_memory import DefaultShortTermMemory  # type: ignore  # noqa: E402


class CodingExecutorAgent(AgentBase):
    """AgentBase adapter that lets Claude Code / Codex participate in plan runs."""

    def __init__(
        self,
        *,
        profile: AgentRuntimeProfile,
        name: str,
        description: str = "",
        store,
        streams: EventStreamService,
        run_id_provider: Callable[[str], str],
    ) -> None:
        memory = DefaultShortTermMemory(["agent_history", "tool_respond"])
        context = ContextEngine(
            providers=[
                HistoryProvider(memory, "agent_history", FullHistoryStrategy() | RecencyStrategy(15)),
                UserPromptProvider(),
            ],
            memory=memory,
        )
        super().__init__(id=profile.agent_id, name=name, llm=None, context=context)
        self.profile = profile
        self.description = description
        self._store = store
        self._streams = streams
        self._run_id_provider = run_id_provider
        self._loaded_history_key: tuple[str, str] | None = None
        if profile.workdir:
            self.work_path = profile.workdir

    async def start(self, prompt: str) -> None:
        self.prepare_start(prompt, keep_history=True)
        run_id = self._run_id_provider(self.id)
        self._load_runtime_history(run_id)
        final_prompt = self.context_engine.build(self.states) or prompt
        runner = runner_for_kind(self.profile.agent_kind)
        if runner is None:
            self._mark_failed(f"不支持的 coding agent: {self.profile.agent_kind}", run_id)
            return

        final_chunks: list[str] = []
        final_text = ""
        failed = ""
        emitted_final = False
        try:
            async for event in runner.run(
                prompt=final_prompt,
                workdir=self.profile.workdir or self.work_path,
                permission_profile=self.profile.permission_profile,
            ):
                payload = {
                    "run_id": run_id,
                    "agent_id": self.id,
                    "agent_kind": self.profile.agent_kind,
                    **event.payload,
                }
                if event.type == "agent.delta":
                    final_chunks.append(str(payload.get("delta", "")))
                elif event.type == "agent.final":
                    final_text = str(payload.get("final", "")) or final_text
                    emitted_final = True
                elif event.type == "agent.failed":
                    failed = str(payload.get("stderr") or payload.get("error") or "Coding agent 执行失败")
                self._publish(run_id, event.type, payload)
        except Exception as exc:
            self._mark_failed(str(exc), run_id)
            return

        if failed:
            self._mark_failed(failed, run_id)
            return

        final = final_text or "".join(final_chunks).strip() or "Coding agent 执行完成"
        self.states["is_finished"] = True
        self.states["finish_reason"] = "Coding agent 执行完成"
        self.states["final"] = final
        self.store_dialogue_history(prompt, final)
        if not emitted_final:
            self._publish(
                run_id,
                "agent.final",
                {
                    "run_id": run_id,
                    "agent_id": self.id,
                    "agent_kind": self.profile.agent_kind,
                    "final": final,
                },
            )

    def _load_runtime_history(self, run_id: str) -> None:
        if not run_id:
            return
        run = self._store.find_one("runs", {"run_id": run_id}) or {}
        conversation_id = run.get("conversation_id")
        message_id = run.get("message_id")
        if not conversation_id or not message_id:
            return
        key = (conversation_id, message_id)
        if self._loaded_history_key == key:
            return

        memory = self.context_engine.get_memory()
        memory.clear_field("agent_history")
        messages = self._store.find_many(
            "messages",
            {"conversation_id": conversation_id},
            sort=[("created_at", 1)],
        )
        for message in messages:
            if message.get("message_id") == message_id:
                break
            if message.get("role") in {"user", "assistant"}:
                memory.store("agent_history", "dialogue", self._format_history_message(message))
        self._loaded_history_key = key

    def _format_history_message(self, message: dict[str, Any]) -> str:
        role = "用户" if message.get("role") == "user" else "Agent"
        return f"### 历史消息\n{role}：{message.get('content', '')}"

    def _mark_failed(self, error: str, run_id: str) -> None:
        self.states["is_finished"] = False
        self.states["finish_reason"] = error
        self.states["final"] = ""
        self._publish(
            run_id,
            "agent.failed",
            {
                "run_id": run_id,
                "agent_id": self.id,
                "agent_kind": self.profile.agent_kind,
                "error": error,
            },
        )

    def _publish(self, run_id: str, name: str, payload: dict[str, Any]) -> None:
        if not run_id:
            return
        self._streams.publish(run_id, name, payload)
