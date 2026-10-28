from __future__ import annotations

import asyncio
import time
import uuid

from application.services.events import EventStreamService
from infra.runtime.control import current_execution_guard, ensure_execution_active, ExecutionRevoked


class HumanConfirmationService:
    """Approval records are shared; only the waiting execution lives locally."""

    def __init__(self, streams: EventStreamService):
        self._streams = streams
        self.runtime = streams.runtime

    async def request_confirmation(self, *, run_id, agent_id, tool_name, called_event_name, arguments):
        item = dict(confirmation_id=str(uuid.uuid4()), run_id=run_id, agent_id=agent_id,
                    tool_name=tool_name, called_event_name=called_event_name,
                    arguments=arguments, status="pending", created_at=time.time())
        try:
            await self.runtime.retry_redis(lambda: self.runtime.save_confirmation(item), revalidate=True)
            # Publication now awaits Redis queueing; cancellation in that window
            # must resolve the already-created shared approval as well.
            await self._streams.publish(run_id, "human.confirmation.requested", item)
            while True:
                await ensure_execution_active()
                current = await self.runtime.retry_redis(lambda: self.runtime.get_confirmation(item["confirmation_id"]),
                                                         revalidate=True)
                if not current:
                    return {"approved": False, "reason": "确认请求已删除"}
                if current["status"] != "pending":
                    return {"approved": current["approved"], "reason": current["reason"]}
                await asyncio.sleep(0.5)
        except asyncio.CancelledError as exc:
            if not isinstance(exc, ExecutionRevoked) and exc.args not in {('execution_revoked',), ('worker_shutdown',)}:
                binding = current_execution_guard.set(None)
                try:
                    try:
                        await self.runtime.retry_redis(lambda: self.resolve(
                            run_id=run_id, confirmation_id=item["confirmation_id"],
                            approved=False, reason="运行已取消"))
                    except KeyError:
                        pass  # Cancellation may precede the initial save.
                finally:
                    current_execution_guard.reset(binding)
            raise

    async def request_approval(self, **kwargs):
        return await self.request_confirmation(**kwargs)

    async def list_pending(self, run_id):
        return await self.runtime.confirmations(run_id)

    async def resolve(self, *, run_id, confirmation_id, approved, reason=""):
        item, changed = await self.runtime.resolve_confirmation(
            run_id, confirmation_id, approved, reason or ("用户已确认" if approved else "用户拒绝执行"))
        if changed:
            await self._streams.publish(run_id, "human.confirmation.resolved", item)
        return item
