"""Host policy adapters; agent_flow remains unaware of IM conversation settings."""
from __future__ import annotations

import copy

from application.services.agents import AgentFactoryService
from application.services.memory_runtime import RunMemoryCoordinator
from domain.run_context import current_run_id
from domain.context.providers import ContextProvider


class RunWorkspaceProvider(ContextProvider):
    name = "run_workspace"

    def __init__(self, workdir):
        self.content = f"## 本次任务工作目录\n{workdir}\n本次任务涉及的文件和命令使用此目录。"

    def get(self, state):
        return [self.content]


class IMAgentFactoryService(AgentFactoryService):
    def build_run_agent(self, agent_id):
        record = self.get_agent_record(agent_id)
        if record is None:
            raise KeyError(f"Agent 不存在: {agent_id}")
        record = copy.deepcopy(record)
        run = self._store.find_one("runs", {"run_id": current_run_id.get()}) or {}
        workdir = (run.get("run_options") or {}).get("workdir")
        if workdir:
            record.setdefault("metadata", {})["workdir"] = workdir
        engine = self._contexts.build_engine(record["context_id"])
        agent = self._construct_agent(record, engine)
        if workdir:
            agent.inject_attribute(work_path=workdir)
            agent.context_engine._providers.insert(0, RunWorkspaceProvider(workdir))
        return agent


class IMRunMemoryCoordinator(RunMemoryCoordinator):
    async def archive(self, record):
        if not (record.get("run_options") or {}).get("memory_write_enabled", False):
            self._status(record["run_id"], memory_status="skipped", memory_reason="automatic_archiving_disabled")
            return
        await super().archive(record)
