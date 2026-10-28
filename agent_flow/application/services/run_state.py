"""Database-owned run state; Redis only caches snapshots and controls execution."""
import asyncio
import logging
import time
from infra.runtime.control import ExecutionRevoked, current_execution_guard, ensure_execution_active
from redis.exceptions import RedisError


class RunStateService:
    def __init__(self, store, runtime, *, long_memory=None, memory_coordinator=None):
        self.store, self.runtime = store, runtime
        self.long_memory = long_memory
        self.memory_coordinator = memory_coordinator

    async def get(self, run_id):
        record = await self.runtime.cache.get(run_id, lambda: self.store.find_one('runs', {'run_id': run_id}))
        if not record:
            return None
        # A cancellation request is a live control signal, not a business status.
        if record.get('status') not in {'pending', 'running'}:
            return {**record, 'cancel_requested': False}
        try:
            control = await asyncio.wait_for(self.runtime.get_state(record.get('kind', 'orchestration'), run_id), 0.5)
        except (RedisError, OSError, TimeoutError):
            return {**record, 'cancel_requested': False,
                    'execution_health': {'status': 'unavailable', 'observed_at': time.time()}}
        health = (control or {}).get('execution_health', {'status': 'healthy', 'failed_probes': 0})
        return {**record, 'cancel_requested': bool(control and control.get('cancel_requested')),
                'execution_health': {**health, 'observed_at': time.time()}}

    async def create(self, record):
        item = self.store.insert_one('runs', record)
        await self.runtime.cache.invalidate(record['run_id'])
        return item

    async def update(self, run_id, changes):
        guard = current_execution_guard.get()
        if guard is not None and not guard.finalizing:
            await ensure_execution_active()
        # Terminal states are absorbing. Even a delayed owner cannot overwrite
        # another finalizer or mutate the finished plan of an old attempt.
        item = await asyncio.to_thread(self.store.update_one, 'runs',
            {'run_id': run_id, 'status': {'$in': ['pending', 'running']}}, changes)
        if item is None:
            if self.store.find_one('runs', {'run_id': run_id}) is not None:
                raise ExecutionRevoked(f'Run 已结束: {run_id}')
            raise KeyError(f'Run 不存在: {run_id}')
        guard = current_execution_guard.get()
        if (changes.get('status') in {'finished', 'failed', 'cancelled'} and
                guard is not None and guard.target_id == run_id):
            guard.commit_terminal()
        await self.runtime.cache.invalidate(run_id)
        return item

    async def delete(self, run_id):
        record = self.store.find_one('runs', {'run_id': run_id}) or {}
        kind = record.get('kind', 'orchestration')
        control = await self.runtime.get_state(kind, run_id)
        if control and control.get('status') in {'pending', 'running'} and control.get('owner_worker'):
            await self.runtime.request_cancel(kind, run_id)
            for _ in range(50):
                await asyncio.sleep(0.1)
                control = await self.runtime.get_state(kind, run_id)
                if not control or control.get('status') not in {'pending', 'running'}:
                    break
            else:
                raise ValueError('执行仍在停止中，请稍后重试删除')
        if self.long_memory is not None:
            await asyncio.to_thread(self.long_memory.delete_sources, run_id=run_id)
        event_count = await self.runtime.journal.delete('run', run_id)
        scope_id = record.get('scope_id') or run_id
        scope_count = await self.runtime.remove_projected(scope_id, lambda event: event.get('run_id') == run_id)
        stats = {
            'events': event_count,
            'scope_events': scope_count,
            'runs': self.store.delete_one('runs', {'run_id': run_id}),
        }
        await self.runtime.delete_runtime(run_id, kind=kind)
        return stats

    async def finish_control(self, run_id):
        """Release only after final messages/events, so deletion can wait for the owner."""
        record = self.store.find_one('runs', {'run_id': run_id})
        if not record or record.get('status') not in {'finished', 'failed', 'cancelled'}:
            return
        if self.memory_coordinator is not None:
            await self.memory_coordinator.archive(record)
            try:
                await self.runtime.cache.invalidate(run_id)
            except Exception:
                logging.getLogger(__name__).exception('Memory status cache invalidation failed: %s', run_id)
        try:
            await asyncio.wait_for(self.runtime.put_state(record.get('kind', 'orchestration'), run_id,
                                   {'status': record['status'], 'cancel_requested': False}), 1)
        except (RedisError, OSError, TimeoutError):
            logging.getLogger(__name__).exception('Database finalized; control release failed: %s', run_id)
