from __future__ import annotations

from typing import Any

from im_backend.application.services.platform.cleanup import IMCleanupService
from im_backend.domain.common import AgentKind
from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge
from im_backend.infra.static_configs.context_templates import agent_context_template


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

        # native Agent 一律按模版克隆一份独立的上下文管理 / 记忆，不再复用传入的 context_id；
        # executor 选了具体工具/字段时，在模版基础上限定 available_tools。
        # 第三方 Agent（claude_code / codex）由各自 CLI 自管上下文，沿用默认 context。
        effective_context_id = context_id
        if agent_kind == "native":
            effective_context_id = self._build_agent_context(
                name=name.strip(),
                agent_type=agent_type,
                tool_names=tool_names or [],
                tool_fields=tool_fields or [],
                owner_user_id=owner_user_id,
            )
        elif agent_kind in {"claude_code", "codex"}:
            # coding agent 克隆一份独立的 "coding" 上下文（含 user_prompt / pinned_context /
            # artifact_protocol / history），使其与 native agent 一样通过 provider 统一管理上下文，
            # 并能注入收藏/回复/引用等消息操作。
            effective_context_id = self._build_coding_context(
                name=name.strip(),
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

    def _build_agent_context(
        self,
        *,
        name: str,
        agent_type: str,
        tool_names: list[str],
        tool_fields: list[str],
        owner_user_id: str = "",
    ) -> str:
        """按上下文模版为新建 native Agent 克隆一份独立的上下文管理 / 记忆。

        模版来自 ``context_templates``（对齐 static_agents.py 的 provider 配置），
        executor 选了具体工具/字段时，在模版基础上把 available_tools 限定为所选项。
        """
        kind = "planner" if agent_type == "planner" else "executor"
        provider_config = agent_context_template(kind)
        if kind == "executor" and (tool_names or tool_fields):
            tool_params = {
                "available_fields": list(tool_fields or []),
                "available_tools": list(tool_names or []),
            }
            replaced = False
            for item in provider_config:
                if item.get("provider_id") == "available_tools":
                    item["params"] = tool_params
                    item["enabled"] = True
                    replaced = True
            if not replaced:
                provider_config.append({"provider_id": "available_tools", "enabled": True, "params": tool_params})
        record = self._bridge.contexts.create_context(
            kind=kind,
            name=f"{name} 上下文",
            provider_config=provider_config,
        )
        context_id = record["context_id"]
        if owner_user_id:
            self._bridge.store.update_one(
                "contexts",
                {"context_id": context_id},
                {"metadata": {"owner_user_id": owner_user_id, "visibility": "private", "kind_label": "agent_context"}},
            )
        return context_id

    def _build_coding_context(self, *, name: str, owner_user_id: str = "") -> str:
        """为 coding agent（claude_code / codex）克隆一份独立的 "coding" 上下文 / 记忆。

        provider 配置单一来源于 ``ContextService.default_template("coding")``，避免与
        im_backend 侧重复定义产生漂移。
        """
        record = self._bridge.contexts.create_context(
            kind="coding",
            name=f"{name} 上下文",
            provider_config=self._bridge.contexts.default_template("coding"),
        )
        context_id = record["context_id"]
        if owner_user_id:
            self._bridge.store.update_one(
                "contexts",
                {"context_id": context_id},
                {"metadata": {"owner_user_id": owner_user_id, "visibility": "private", "kind_label": "agent_context"}},
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
