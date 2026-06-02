from __future__ import annotations

from typing import Any

from im_backend.application.services.platform.cleanup import IMCleanupService
from im_backend.domain.common import AgentKind
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class IMAgentService:
    PROTECTED_AGENT_IDS = {"default_planner", "default_executor"}
    AGENT_KINDS: set[AgentKind] = {"native", "claude_code", "codex", "human_proxy"}

    def __init__(self, *, bridge: AgentFlowBridge, cleanup: IMCleanupService) -> None:
        self._bridge = bridge
        self._cleanup = cleanup

    def list_agents(self) -> list[dict[str, Any]]:
        return self._bridge.list_agents()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "field": tool.get("field"),
            }
            for tool in self._bridge.list_tools()
        ]

    def list_visible_agents(self, user_id: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self._bridge.list_agents()
            if self.is_visible(record, user_id)
        ]

    def list_contexts(self) -> list[dict[str, Any]]:
        return self._bridge.list_contexts()

    def list_visible_contexts(self, user_id: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self._bridge.list_contexts()
            if self.is_visible(record, user_id)
        ]

    def create_agent(
        self,
        *,
        name: str,
        agent_type: str = "executor",
        context_id: str = "default_executor",
        role_prompt: str = "",
        metadata: dict[str, Any] | None = None,
        owner_user_id: str = "",
        tool_names: list[str] | None = None,
        tool_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Agent 名称不能为空")
        if agent_type not in {"executor", "planner"}:
            raise ValueError("agent_type 必须是 executor 或 planner")
        requested_metadata = metadata or {}
        agent_kind = requested_metadata.get("agent_kind") or "native"
        if agent_kind not in self.AGENT_KINDS:
            raise ValueError("agent_kind 必须是 native、claude_code、codex 或 human_proxy")
        if agent_kind != "native" and agent_type != "executor":
            raise ValueError("第三方 Agent 只能创建为 executor")

        # 选了具体工具/字段时，为该 native executor 单独克隆一个限定工具的 context。
        effective_context_id = context_id
        if agent_kind == "native" and agent_type == "executor" and (tool_names or tool_fields):
            effective_context_id = self._build_tool_context(
                name=name.strip(),
                tool_names=tool_names or [],
                tool_fields=tool_fields or [],
                owner_user_id=owner_user_id,
            )
        elif owner_user_id:
            self.ensure_context_access(effective_context_id, owner_user_id)

        agent_metadata = {
            **requested_metadata,
            "agent_kind": agent_kind,
        }
        if owner_user_id:
            agent_metadata = {
                **agent_metadata,
                "owner_user_id": owner_user_id,
                "visibility": "private",
            }
        return self._bridge.create_agent(
            name=name.strip(),
            agent_type=agent_type,
            context_id=effective_context_id,
            role_prompt=role_prompt,
            metadata=agent_metadata,
        )

    def _build_tool_context(
        self,
        *,
        name: str,
        tool_names: list[str],
        tool_fields: list[str],
        owner_user_id: str = "",
    ) -> str:
        """克隆 executor 默认模板，把 available_tools provider 限定为所选工具/字段。"""
        contexts = self._bridge.contexts
        template = contexts.default_template("executor")
        tool_params = {
            "available_fields": list(tool_fields or []),
            "available_tools": list(tool_names or []),
        }
        replaced = False
        for item in template:
            if item.get("provider_id") == "available_tools":
                item["params"] = tool_params
                item["enabled"] = True
                replaced = True
        if not replaced:
            template.append({"provider_id": "available_tools", "enabled": True, "params": tool_params})
        record = contexts.create_context(
            kind="executor",
            name=f"{name} 工具集",
            provider_config=template,
        )
        context_id = record["context_id"]
        if owner_user_id:
            self._bridge.store.update_one(
                "contexts",
                {"context_id": context_id},
                {"metadata": {"owner_user_id": owner_user_id, "visibility": "private", "kind_label": "tool_set"}},
            )
        return context_id

    def delete_agent(self, agent_id: str, *, user_id: str = "") -> dict[str, Any]:
        if agent_id in self.PROTECTED_AGENT_IDS:
            raise ValueError("默认 Agent 不允许删除")
        record = self._bridge.ensure_agent_exists(agent_id)
        if user_id and self.owner_user_id(record) != user_id:
            raise ValueError("只能删除当前用户拥有的 Agent")
        agent_flow_result = self._bridge.delete_agent(agent_id)
        im_stats = self._cleanup.delete_agent_im_refs(agent_id)
        return {
            "deleted": True,
            "agent_id": agent_id,
            "agent_flow": agent_flow_result,
            "im_stats": im_stats,
        }

    def ensure_agent_access(self, agent_id: str, user_id: str) -> dict[str, Any]:
        record = self._bridge.ensure_agent_exists(agent_id)
        if not self.is_visible(record, user_id):
            raise KeyError(f"Agent 不存在: {agent_id}")
        return record

    def ensure_context_access(self, context_id: str, user_id: str) -> dict[str, Any]:
        record = self._bridge.get_context_record(context_id)
        if record is None or not self.is_visible(record, user_id):
            raise KeyError(f"Context 不存在: {context_id}")
        return record

    def is_visible(self, record: dict[str, Any], user_id: str) -> bool:
        metadata = record.get("metadata") or {}
        if metadata.get("visibility") == "public":
            return True
        owner = self.owner_user_id(record)
        return not owner or owner == user_id

    def owner_user_id(self, record: dict[str, Any]) -> str:
        metadata = record.get("metadata") or {}
        return metadata.get("owner_user_id") or metadata.get("created_by") or ""
