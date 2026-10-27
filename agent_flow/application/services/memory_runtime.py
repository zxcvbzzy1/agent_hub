"""Non-fatal long-term memory integration shared by orchestration and DM runs."""
from __future__ import annotations

import asyncio
import logging

from domain.memory.long.providers import MemoryDocumentProvider
from domain.memory.long.document import MemoryDocumentSnapshot
from domain.context.providers import AvailableToolsProvider

log = logging.getLogger(__name__)


class RunMemoryCoordinator:
    def __init__(self, memory, store, events):
        self.memory, self.store, self.events = memory, store, events

    def _status(self, run_id: str, **changes):
        try:
            self.store.update_one("runs", {"run_id": run_id}, changes)
        except Exception:
            log.exception("Cannot record long-term memory status for %s", run_id)

    async def prepare(self, record: dict) -> MemoryDocumentSnapshot:
        scope = record.get("memory_scope")
        if self.memory is None or not scope or not scope.get("user_id"):
            self._status(record["run_id"], memory_status="skipped", memory_reason="missing_trusted_user_scope")
            return MemoryDocumentSnapshot()
        try:
            if self.memory.documents is None:
                return MemoryDocumentSnapshot()
            snapshot = await asyncio.to_thread(self.memory.documents.snapshot, scope["user_id"])
            self._status(record["run_id"], memory_document_revision=snapshot.revision,
                         memory_document_path=snapshot.file_path, memory_document_error="")
            return snapshot
        except Exception as exc:
            log.exception("Memory document load failed for %s", record["run_id"])
            self._status(record["run_id"], memory_document_error=str(exc))
            return MemoryDocumentSnapshot()

    async def inject(self, agent, snapshot: MemoryDocumentSnapshot, run_id: str) -> None:
        if self.memory is not None and not any(isinstance(p, AvailableToolsProvider) and
                ("manage_memory" in p._tools or "memory" in p._fields) for p in agent.context_engine._providers):
            agent.context_engine._providers.append(AvailableToolsProvider([], ["manage_memory"]))
        enabled = False
        for provider in agent.context_engine._providers:
            if isinstance(provider, MemoryDocumentProvider):
                provider.content = snapshot.content
                enabled = enabled or provider.enabled
        if enabled and snapshot.block_ids and self.memory is not None:
            try:
                await asyncio.to_thread(self.memory.repository.mark_used, list(snapshot.block_ids), run_id)
            except Exception:
                log.exception("Long-term usage accounting failed for %s", run_id)

    async def archive(self, record: dict) -> None:
        scope = record.get("memory_scope")
        if self.memory is None or not scope or not scope.get("user_id"):
            self._status(record["run_id"], memory_status="skipped", memory_reason="missing_trusted_user_scope")
            return
        if record.get("memory_status") == "ready":
            return
        try:
            events = await self.events.list_events(record["run_id"], user_id=scope["user_id"])
            source = await asyncio.to_thread(self.memory.archive_run, record, events)
            self._status(record["run_id"], memory_status=source["index_status"], memory_source_id=source["source_id"], memory_error="")
        except Exception as exc:
            log.exception("Long-term archive failed for %s", record["run_id"])
            self._status(record["run_id"], memory_status="failed", memory_error=str(exc))
