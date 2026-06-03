from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from im_backend.domain.models import AgentRuntimeProfile
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
from im_backend.infra.coding_agents.artifacts_protocol import ArtifactStreamParser
from im_backend.infra.coding_agents.runners import runner_for_kind

ensure_agent_flow_path()

from application.services.events import EventStreamService  # type: ignore  # noqa: E402
from domain.agent_base import AgentBase  # type: ignore  # noqa: E402
from domain.context.context import ContextEngine  # type: ignore  # noqa: E402
from infra.tool.builtin.artifacts import InlineArtifactTool  # type: ignore  # noqa: E402


class CodingExecutorAgent(AgentBase):
    """AgentBase adapter that lets Claude Code / Codex participate in plan runs."""

    def __init__(
        self,
        *,
        profile: AgentRuntimeProfile,
        name: str,
        context_engine: ContextEngine,
        description: str = "",
        store,
        streams: EventStreamService,
        run_id_provider: Callable[[str], str],
    ) -> None:
        # ContextEngine 由 ContextService 按 "coding" 模版构建（含 user_prompt / pinned_context /
        # artifact_protocol / history(agent_history)），不再在此硬编码 provider 列表。
        super().__init__(id=profile.agent_id, name=name, llm=None, context=context_engine)
        self.profile = profile
        self.description = description
        self._store = store
        self._streams = streams
        self._run_id_provider = run_id_provider
        self._loaded_history_key: tuple[str, str] | None = None
        if profile.workdir:
            self.work_path = profile.workdir

    async def start(self, prompt: str) -> None:
        await self._run_coding_agent(prompt, load_runtime_history=True)

    async def start_with_history(self, prompt: str) -> None:
        await self._run_coding_agent(prompt, load_runtime_history=False)

    async def _run_coding_agent(self, prompt: str, *, load_runtime_history: bool) -> None:
        self.prepare_start(prompt, keep_history=True)
        run_id = self._run_id_provider(self.id)
        if load_runtime_history:
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
        delta_parser = ArtifactStreamParser()
        final_parser = ArtifactStreamParser()
        seen_artifacts: set[str] = set()
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
                    clean, markers = delta_parser.feed(str(payload.get("delta", "")))
                    self._emit_artifacts(run_id, markers, seen_artifacts)
                    if not clean:
                        continue
                    final_chunks.append(clean)
                    payload["delta"] = clean
                    self._publish(run_id, "agent.delta", payload)
                    continue
                if event.type == "agent.final":
                    clean, markers = final_parser.feed(str(payload.get("final", "")))
                    tail_clean, tail_markers = final_parser.flush()
                    clean += tail_clean
                    self._emit_artifacts(run_id, markers + tail_markers, seen_artifacts)
                    final_text = clean or final_text
                    emitted_final = True
                    payload["final"] = clean
                    self._publish(run_id, "agent.final", payload)
                    continue
                if event.type == "agent.failed":
                    failed = str(payload.get("stderr") or payload.get("error") or "Coding agent 执行失败")
                self._publish(run_id, event.type, payload)
        except Exception as exc:
            self._mark_failed(str(exc), run_id)
            return

        # 冲刷流式缓冲里残留的标记/文本
        tail_clean, tail_markers = delta_parser.flush()
        self._emit_artifacts(run_id, tail_markers, seen_artifacts)
        if tail_clean:
            final_chunks.append(tail_clean)
            self._publish(
                run_id,
                "agent.delta",
                {
                    "run_id": run_id,
                    "agent_id": self.id,
                    "agent_kind": self.profile.agent_kind,
                    "delta": tail_clean,
                },
            )

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

    def _emit_artifacts(
        self,
        run_id: str,
        markers: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        """把解析出的标记块复用 InlineArtifactTool 构造成 artifacts.<type> 事件。

        seen 用于去重：delta 流与 final 复述里可能出现同一个标记块，只发一次。
        """
        for marker in markers:
            key = json.dumps(marker, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            try:
                artifact_payload = InlineArtifactTool().build_event_payload(
                    {**marker, "agent_id": self.id, "run_id": run_id}
                )
            except Exception as exc:
                self._publish(
                    run_id,
                    "artifact.failed",
                    {
                        "run_id": run_id,
                        "agent_id": self.id,
                        "agent_kind": self.profile.agent_kind,
                        "error": str(exc),
                        "marker": marker,
                    },
                )
                continue
            self._publish(run_id, artifact_payload["event_name"], artifact_payload)

    def _publish(self, run_id: str, name: str, payload: dict[str, Any]) -> None:
        if not run_id:
            return
        self._streams.publish(run_id, name, payload)
