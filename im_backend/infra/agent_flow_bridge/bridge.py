from __future__ import annotations

from pathlib import Path
from typing import Any

from im_backend.domain.models import AgentRuntimeProfile
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
from im_backend.infra.coding_agents.executor_agent import CodingExecutorAgent
from im_backend.infra.env import load_backend_env

load_backend_env()
ensure_agent_flow_path()

from application.events.bridge import FrontendEventBridge  # type: ignore  # noqa: E402
from application.events.human_confirmation import HumanConfirmationService  # type: ignore  # noqa: E402
from application.services.agents import AgentFactoryService  # type: ignore  # noqa: E402
from application.services.contexts import ContextService  # type: ignore  # noqa: E402
from application.services.conversations import ConversationService  # type: ignore  # noqa: E402
from application.services.events import EventStreamService  # type: ignore  # noqa: E402
from application.services.runs import RunOrchestrationService  # type: ignore  # noqa: E402
from application.services.tools import ToolRegistryService  # type: ignore  # noqa: E402
from domain.runtime_hooks import (  # type: ignore  # noqa: E402
    register_human_approval_provider,
    register_run_context_provider,
    register_tool_event_observer,
)
from infra.config import factory, llm_client  # type: ignore  # noqa: E402


class AgentFlowBridge:
    """Convenience facade around agent_flow services.

    im_backend may import stable agent_flow domain/application/infra modules
    directly; this facade remains useful for shared container setup and common
    runtime calls.
    """

    def __init__(self, *, store, repo_root: str | Path) -> None:
        self._store = store
        self._root_dir = Path(repo_root).resolve()
        self.events = EventStreamService(self._store)
        self.frontend_bridge = FrontendEventBridge(self.events, factory)
        self.human_confirmations = HumanConfirmationService(self.events)
        register_tool_event_observer(self.frontend_bridge)
        register_human_approval_provider(self.human_confirmations)
        register_run_context_provider(self.frontend_bridge)
        self.tools = ToolRegistryService(self._store, self._root_dir / "agent_flow")
        self.contexts = ContextService(self._store)
        self.agents = AgentFactoryService(
            self._store,
            self.contexts,
            llm_client,
            self.events,
            external_executor_builder=self._build_external_executor,
        )
        self.runs = RunOrchestrationService(
            self._store,
            self.agents,
            self.contexts,
            self.events,
            self.frontend_bridge,
        )
        self.conversations = ConversationService(self._store)

    @property
    def store(self):
        return self._store

    def list_agents(self) -> list[dict[str, Any]]:
        return self.agents.list_agents()

    def list_contexts(self) -> list[dict[str, Any]]:
        return self.contexts.list_contexts()

    def get_context_record(self, context_id: str) -> dict[str, Any] | None:
        return self.contexts.get_context(context_id)

    def context_exists(self, context_id: str) -> bool:
        return self.get_context_record(context_id) is not None

    def agent_exists(self, agent_id: str) -> bool:
        return self.get_agent_record(agent_id) is not None

    def create_context_from_engine(
        self,
        *,
        kind: str,
        name: str,
        engine,
        context_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.contexts.create_context_from_engine(
            kind=kind,
            name=name,
            engine=engine,
            context_id=context_id,
        )
        if metadata:
            self._store.update_one(
                "contexts",
                {"context_id": record["context_id"]},
                {"metadata": metadata},
            )
            record = self.contexts.get_context(record["context_id"]) or record
        return record

    def get_agent_record(self, agent_id: str) -> dict[str, Any] | None:
        return self.agents.get_agent_record(agent_id)

    def get_agent(self, agent_id: str):
        return self.agents.get_agent(agent_id)

    def _build_external_executor(self, record: dict[str, Any]):
        profile = AgentRuntimeProfile.from_agent_record(record)
        if not profile.workdir:
            profile.workdir = str(self._root_dir.parent)
        return CodingExecutorAgent(
            profile=profile,
            name=record.get("name", profile.agent_id),
            description=(record.get("metadata") or {}).get("description", ""),
            store=self._store,
            streams=self.events,
            run_id_provider=self.frontend_bridge.run_id_for_agent,
        )

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
        return self.agents.create_agent(
            name=name,
            agent_type=agent_type,
            context_id=context_id,
            role_prompt=role_prompt,
            metadata=metadata or {},
        )

    def create_agent_from_instance(
        self,
        *,
        agent,
        agent_type: str | None = None,
        context_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if context_id and self.context_exists(context_id):
            agent_type = agent_type or ("planner" if type(agent).__name__ == "PlanAgent" else "executor")
            if agent_type not in {"planner", "executor"}:
                raise ValueError("agent_type 必须是 planner 或 executor")
            record = {
                "agent_id": agent.id,
                "name": agent.name,
                "agent_type": agent_type,
                "context_id": context_id,
                "role_prompt": rp if isinstance(rp := getattr(agent, "_role_prompt", ""), str) else "",
                "metadata": {
                    "description": getattr(agent, "description", ""),
                    "imported_agent_class": type(agent).__name__,
                    **(metadata or {}),
                },
            }
            self._store.update_one("agents", {"agent_id": agent.id}, record, upsert=True)
            agent._llm = self.agents._build_llm(record)
            self.agents._agents[agent.id] = agent
            return record
        return self.agents.create_agent_from_instance(
            agent=agent,
            agent_type=agent_type,
            context_id=context_id,
            metadata=metadata or {},
        )

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        return self.agents.delete_agent(agent_id)

    def create_runtime_conversation(self, *, title: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return self.conversations.create_conversation(title=title, metadata=metadata)

    def add_runtime_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.conversations.add_message(
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
        return self.runs.create_run(
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

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        return self.runs.cancel_run(run_id)

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        return self.events.list_events(run_id)

    def register_agent_runtime_scope(self, agent_id: str, scope_id: str) -> None:
        self.frontend_bridge.register_agent_run(agent_id, scope_id)

    def unregister_agent_runtime_scope(self, agent_id: str, scope_id: str) -> None:
        self.frontend_bridge.unregister_agent_run(agent_id, scope_id)
