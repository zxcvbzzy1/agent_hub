from __future__ import annotations

from typing import Any

from im_backend.application.services.cleanup import IMCleanupService
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class IMAgentService:
    PROTECTED_AGENT_IDS = {"default_planner", "default_executor"}

    def __init__(self, *, bridge: AgentFlowBridge, cleanup: IMCleanupService) -> None:
        self._bridge = bridge
        self._cleanup = cleanup

    def list_agents(self) -> list[dict[str, Any]]:
        return self._bridge.list_agents()

    def list_contexts(self) -> list[dict[str, Any]]:
        return self._bridge.list_contexts()

    def create_agent(
        self,
        *,
        name: str,
        agent_type: str = "executor",
        context_id: str = "default_executor",
        role_prompt: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Agent 名称不能为空")
        if agent_type not in {"executor", "planner"}:
            raise ValueError("agent_type 必须是 executor 或 planner")
        return self._bridge.create_agent(
            name=name.strip(),
            agent_type=agent_type,
            context_id=context_id,
            role_prompt=role_prompt,
            metadata={"agent_kind": "native", **(metadata or {})},
        )

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        if agent_id in self.PROTECTED_AGENT_IDS:
            raise ValueError("默认 Agent 不允许删除")
        self._bridge.ensure_agent_exists(agent_id)
        agent_flow_result = self._bridge.delete_agent(agent_id)
        im_stats = self._cleanup.delete_agent_im_refs(agent_id)
        return {
            "deleted": True,
            "agent_id": agent_id,
            "agent_flow": agent_flow_result,
            "im_stats": im_stats,
        }
