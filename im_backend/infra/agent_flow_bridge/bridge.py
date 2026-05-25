from __future__ import annotations

import os
from typing import Any

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path

ensure_agent_flow_path()
os.environ.setdefault("GLM_API", "im-backend-placeholder")
os.environ.setdefault("DEEPSEEK_API", "im-backend-placeholder")
os.environ.setdefault("MINIMAX_API", "im-backend-placeholder")

from api.core.dependencies import get_container  # type: ignore  # noqa: E402


class AgentFlowBridge:
    """Small facade around agent_flow services.

    Keeping all agent_flow imports behind this adapter lets the IM backend stay
    independently structured while still reusing the existing agent runtime.
    """

    def __init__(self) -> None:
        self._container = get_container()

    @property
    def store(self):
        return self._container.store

    @property
    def events(self):
        return self._container.events

    def list_agents(self) -> list[dict[str, Any]]:
        return self._container.agents.list_agents()

    def get_agent_record(self, agent_id: str) -> dict[str, Any] | None:
        return self._container.agents.get_agent_record(agent_id)

    def ensure_agent_exists(self, agent_id: str) -> dict[str, Any]:
        record = self.get_agent_record(agent_id)
        if record is None:
            raise KeyError(f"Agent 不存在: {agent_id}")
        return record

    def create_agent(
        self,
        *,
        name: str,
        agent_type: str = "executor",
        context_id: str = "default_executor",
        role_prompt: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._container.agents.create_agent(
            name=name,
            agent_type=agent_type,
            context_id=context_id,
            role_prompt=role_prompt,
            metadata=metadata or {},
        )

    def create_runtime_conversation(self, *, title: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return self._container.conversations.create_conversation(title=title, metadata=metadata)

    def add_runtime_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._container.conversations.add_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )

    def create_run(
        self,
        *,
        prompt: str,
        mode: str,
        executor_agent_id: str | None = None,
        planner_agent_id: str = "default_planner",
        executor_agent_ids: list[str] | None = None,
        context_id: str = "default_step",
        max_replan_rounds: int = 3,
        conversation_id: str | None = None,
        message_id: str | None = None,
        auto_start: bool = True,
    ) -> dict[str, Any]:
        return self._container.runs.create_run(
            prompt=prompt,
            mode=mode,
            executor_agent_id=executor_agent_id,
            planner_agent_id=planner_agent_id,
            executor_agent_ids=executor_agent_ids or [],
            context_id=context_id,
            max_replan_rounds=max_replan_rounds,
            conversation_id=conversation_id,
            message_id=message_id,
            auto_start=auto_start,
        )

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._container.events.list_events(run_id)
