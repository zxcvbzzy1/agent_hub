from __future__ import annotations

import asyncio
import time
import uuid

from application.services.events import EventStreamService
from infra.runtime.control import current_execution_guard, ensure_execution_active, ExecutionRevoked
from infra.tool.common_func import normalize_questions, validate_question_answers


class HumanConfirmationService:
    """Approval records are shared; only the waiting execution lives locally."""

    def __init__(self, streams: EventStreamService):
        self._streams = streams
        self.runtime = streams.runtime

    async def request_confirmation(self, *, run_id, agent_id, tool_name, called_event_name, arguments,
                                   kind="approval", questions=None):
        item = dict(confirmation_id=str(uuid.uuid4()), run_id=run_id, agent_id=agent_id,
                    tool_name=tool_name, called_event_name=called_event_name,
                    arguments=arguments, kind=kind, status="pending", created_at=time.time())
        if kind == "question":
            item['questions'] = questions
            run = await asyncio.to_thread(self._streams._store.find_one, 'runs', {'run_id': run_id}) or {}
            execution_kind = run.get('kind', 'orchestration')
            control = await self.runtime.retry_redis(lambda: self.runtime.get_state(execution_kind, run_id),
                                                     revalidate=True)
            if not control or control.get('revoked') or control.get('cancel_requested') or control.get('status') not in {'pending', 'running'}:
                raise ValueError("没有有效的运行执行权限")
            item.update(execution_kind=execution_kind, execution_token=control['execution_token'])
        try:
            await self.runtime.retry_redis(lambda: self.runtime.save_confirmation(item), revalidate=True)
            # Publication now awaits Redis queueing; cancellation in that window
            # must resolve the already-created shared approval as well.
            await self.runtime.retry_redis(lambda: self._streams.publish(
                run_id, "human.confirmation.requested", self.public_item(item),
                event_id=self.event_id(item, 'requested')), revalidate=True)
            while True:
                await ensure_execution_active()
                current = await self.runtime.retry_redis(lambda: self.runtime.get_confirmation(item["confirmation_id"]),
                                                         revalidate=True)
                if not current:
                    if kind == 'question':
                        raise asyncio.CancelledError('问题已删除')
                    return {"approved": False, "reason": "确认请求已删除"}
                if current["status"] != "pending":
                    if kind == 'question':
                        await ensure_execution_active()
                        if current.get('answer') is None:
                            raise asyncio.CancelledError(current.get('reason', 'question_cancelled'))
                        return current['answer']
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

    async def request_question(self, **kwargs):
        questions = normalize_questions(kwargs['arguments'].get('questions'))
        return await self.request_confirmation(**kwargs, kind='question', questions=questions)

    @staticmethod
    def public_item(item):
        return {key: value for key, value in item.items() if key not in {'execution_token', 'execution_kind'}}

    @staticmethod
    def event_id(item, phase):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"confirmation:{item['confirmation_id']}:{phase}"))

    async def list_pending(self, run_id):
        return [self.public_item(item) for item in await self.runtime.confirmations(run_id)]

    async def resolve(self, *, run_id, confirmation_id, approved, reason=""):
        current = await self.runtime.get_confirmation(confirmation_id)
        if current and current.get('kind') == 'question' and approved:
            raise ValueError("问题必须通过答案接口提交，不能通过允许执行来回答")
        item, changed = await self.runtime.resolve_confirmation(
            run_id, confirmation_id, approved, reason or ("用户已确认" if approved else "用户拒绝执行"))
        if changed:
            await self._streams.publish(run_id, "human.confirmation.resolved", self.public_item(item),
                                        event_id=self.event_id(item, 'resolved'))
        return self.public_item(item)

    async def answer(self, *, run_id, confirmation_id, answers, attachments=None):
        item = await self.runtime.get_confirmation(confirmation_id)
        if not item or item['run_id'] != run_id or item.get('kind') != 'question':
            raise KeyError('问题不存在')
        run = await asyncio.to_thread(self._streams._store.find_one, 'runs', {'run_id': run_id})
        if not run:
            raise KeyError('运行不存在')
        if item['status'] == 'pending' and run.get('status') not in {'pending', 'running'}:
            raise ValueError('运行已结束，不能提交答案')
        value = {'answers': validate_question_answers(item['questions'], answers), 'attachments': attachments or []}
        item, _ = await self.runtime.resolve_confirmation(run_id, confirmation_id, True, '用户已回答', answer=value)
        if item.get('answer') is None:
            raise ValueError('问题已取消，不能提交答案')
        # Repeat publication repairs a lost ACK; the journal deduplicates this ID.
        await self._streams.publish(run_id, 'human.confirmation.resolved', self.public_item(item),
                                    event_id=self.event_id(item, 'resolved'))
        return self.public_item(item)
