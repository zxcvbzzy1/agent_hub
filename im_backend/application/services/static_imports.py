from __future__ import annotations

from importlib import import_module
from typing import Any

from im_backend.infra.agent_flow_bridge.bridge import AgentFlowBridge


class StaticConfigImportService:
    def __init__(
        self,
        *,
        bridge: AgentFlowBridge,
        module_name: str = "im_backend.infra.static_configs.registry",
    ) -> None:
        self._bridge = bridge
        self._module_name = module_name

    def import_defaults(self) -> dict[str, int]:
        module = import_module(self._module_name)
        stats = {
            "contexts_imported": 0,
            "contexts_skipped": 0,
            "agents_imported": 0,
            "agents_skipped": 0,
        }
        for item in getattr(module, "CONTEXTS", []):
            if self._import_context(item):
                stats["contexts_imported"] += 1
            else:
                stats["contexts_skipped"] += 1

        for item in getattr(module, "AGENTS", []):
            if self._import_agent(item):
                stats["agents_imported"] += 1
            else:
                stats["agents_skipped"] += 1
        return stats

    def _import_context(self, item: dict[str, Any]) -> bool:
        context_id = self._required(item, "context_id")
        if self._bridge.context_exists(context_id):
            return False
        self._bridge.create_context_from_engine(
            kind=self._required(item, "kind"),
            name=self._required(item, "name"),
            engine=self._required(item, "engine"),
            context_id=context_id,
            metadata=self._metadata(item),
        )
        return True

    def _import_agent(self, item: dict[str, Any]) -> bool:
        agent = self._required(item, "agent")
        agent_id = getattr(agent, "id", "")
        if not agent_id:
            raise ValueError("静态 Agent 缺少 id")
        if self._bridge.agent_exists(agent_id):
            return False
        self._bridge.create_agent_from_instance(
            agent=agent,
            agent_type=item.get("agent_type"),
            context_id=item.get("context_id"),
            metadata=self._metadata(item),
        )
        return True

    def _metadata(self, item: dict[str, Any]) -> dict[str, Any]:
        user_id = item.get("user_id") or ""
        return {
            **(item.get("metadata") or {}),
            "owner_user_id": user_id,
            "visibility": "private" if user_id else "public",
            "static_import": True,
        }

    def _required(self, item: dict[str, Any], key: str):
        value = item.get(key)
        if value is None or value == "":
            raise ValueError(f"静态配置缺少字段: {key}")
        return value
