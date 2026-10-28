"""Cross-worker execution leases, cancellation and approval controls."""
from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from redis.exceptions import WatchError, RedisError

log = logging.getLogger(__name__)
ACTIVE = {"pending", "running"}
REDIS_FAILURES = (RedisError, OSError, TimeoutError)


class ExecutionRevoked(asyncio.CancelledError):
    """The execution owner has lost permission; this is not a user cancellation."""


current_execution_guard = ContextVar("execution_guard", default=None)


async def ensure_execution_active():
    guard = current_execution_guard.get()
    if guard is not None:
        await guard()


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str)


class RedisExecutionControl:
    operation_timeout = 5

    CONTROL_FIELDS = frozenset({
        "run_id", "message_id", "agent_id", "conversation_id", "scope_id",
        "owner_worker", "status", "cancel_requested", "started_at", "finished_at",
        "execution_token", "revoked", "execution_health",
    })

    async def _heartbeat(self):
        await self.redis.set(self.key(f"worker:{self.worker_id}"), "alive", ex=self.heartbeat_ttl)

    def track(self, kind, target_id, task):
        identity = f"{kind}:{target_id}"
        self._tasks[identity] = task

        def done(finished):
            if self._tasks.get(identity) is finished:
                self._tasks.pop(identity, None)
                self._claims.pop(identity, None)
                self._finalizing.discard(identity)
            if not finished.cancelled() and finished.exception():
                exc = finished.exception()
                log.error("Runtime task %s failed", identity, exc_info=(type(exc), exc, exc.__traceback__))

        task.add_done_callback(done)

    async def _maintain(self):
        async with asyncio.TaskGroup() as group:
            group.create_task(self._pulse(), name="runtime-heartbeat")
            group.create_task(self._check_local_tasks(), name="runtime-cancellation")
            group.create_task(self._reap(), name="runtime-orphan-probes")

    async def get_state(self, kind, target_id):
        fields = await self.redis.hgetall(self.key(f"control:v2:{kind}:{target_id}"))
        return {k: json.loads(v) for k, v in fields.items()} if fields else None

    async def put_state(self, kind, target_id, changes):
        key = self.key(f"control:v2:{kind}:{target_id}")
        # This hash is a lease/control record, never a business-state cache.
        changes = {k: v for k, v in changes.items() if k in self.CONTROL_FIELDS}
        changes = {**changes, "kind": kind, "target_id": target_id, "updated_at": time.time()}
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping={k: encode(v) for k, v in changes.items()})
            status = changes.get("status")
            if status in ACTIVE:
                pipe.persist(key)
                pipe.sadd(self.key("control:v2:active"), f"{kind}:{target_id}")
            elif status:
                pipe.expire(key, self.retention)
                pipe.srem(self.key("control:v2:active"), f"{kind}:{target_id}")
            await pipe.execute()
        return await self.get_state(kind, target_id)

    async def claim(self, kind, target_id, fields):
        """Atomically start one attempt, allowing an explicit retry of terminal work."""
        fields = {k: v for k, v in fields.items() if k in self.CONTROL_FIELDS}
        await self._heartbeat()
        key = self.key(f"control:v2:{kind}:{target_id}")
        while True:
            async with self.redis.pipeline() as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hget(key, "status")
                    owner = await pipe.hget(key, "owner_worker")
                    if raw and json.loads(raw) in ACTIVE and owner and json.loads(owner):
                        return False
                    record = {**fields, "kind": kind, "target_id": target_id,
                              "owner_worker": self.worker_id, "cancel_requested": False,
                              "execution_token": uuid.uuid4().hex, "revoked": False,
                              "execution_health": {"status": "healthy", "failed_probes": 0},
                              "status": "running", "started_at": time.time(), "updated_at": time.time()}
                    pipe.multi()
                    pipe.delete(key)
                    pipe.hset(key, mapping={k: encode(v) for k, v in record.items()})
                    pipe.sadd(self.key("control:v2:active"), f"{kind}:{target_id}")
                    await pipe.execute()
                    self._claims[f"{kind}:{target_id}"] = record["execution_token"]
                    return True
                except WatchError:
                    continue

    async def active_states(self):
        result = []
        for identity in await self.redis.smembers(self.key("control:v2:active")):
            state = await self.get_state(*identity.split(":", 1))
            if state and state.get("status") in ACTIVE:
                result.append(state)
        return result

    async def request_cancel(self, kind, target_id):
        key = self.key(f"control:v2:{kind}:{target_id}")
        while True:
            async with self.redis.pipeline() as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.hget(key, "status")
                    if raw is None:
                        raise KeyError(f"运行不存在: {target_id}")
                    if json.loads(raw) not in ACTIVE:
                        return await self.get_state(kind, target_id)
                    pipe.multi()
                    pipe.hset(key, "cancel_requested", "true")
                    await pipe.execute()
                    return await self.get_state(kind, target_id)
                except WatchError:
                    continue

    async def reap_orphans(self):
        if self.on_orphan is None:
            return
        for state in await self.active_states():
            state, changed = await self._probe_owner(state)
            if changed and self.on_health is not None:
                try:
                    await asyncio.wait_for(self.on_health(state), self.operation_timeout)
                except REDIS_FAILURES:
                    self.redis_failed()
            if state and state.get("revoked"):
                lock = self.key(f"orphan:{state['kind']}:{state['target_id']}")
                lock_owner = uuid.uuid4().hex
                if await self.redis.set(lock, lock_owner, nx=True, ex=30):
                    try:
                        await self.on_orphan(state)
                    finally:
                        await self.redis.eval("if redis.call('GET', KEYS[1]) == ARGV[1] then "
                                              "return redis.call('DEL', KEYS[1]) end return 0", 1, lock, lock_owner)

    async def save_confirmation(self, item):
        key = self.key(f"confirmation:{item['confirmation_id']}")
        # Retrying a lost ACK must never reset an already resolved approval.
        await self.redis.eval("local old = redis.call('GET', KEYS[1]); "
            "if old then if cjson.decode(old).status ~= 'pending' then return 0 end "
            "else redis.call('SET', KEYS[1], ARGV[1]) end; "
            "return redis.call('SADD', KEYS[2], ARGV[2])", 2, key,
            self.key(f"confirmations:{item['run_id']}"), encode(item), item['confirmation_id'])

    async def get_confirmation(self, confirmation_id):
        raw = await self.redis.get(self.key(f"confirmation:{confirmation_id}"))
        return json.loads(raw) if raw else None

    async def confirmations(self, run_id):
        result = []
        for cid in await self.redis.smembers(self.key(f"confirmations:{run_id}")):
            item = await self.get_confirmation(cid)
            if item and item["status"] == "pending":
                result.append(item)
        return result

    async def resolve_confirmation(self, run_id, confirmation_id, approved, reason, *, answer=None):
        key = self.key(f"confirmation:{confirmation_id}")
        while True:
            async with self.redis.pipeline() as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    item = json.loads(raw) if raw else None
                    if not item or item["run_id"] != run_id:
                        raise KeyError(f"confirmation not found: {confirmation_id}")
                    if item["status"] != "pending":
                        return item, False
                    if answer is not None:
                        # Answer and lease are checked in one transaction. A peer
                        # may revoke the old worker while the browser is submitting.
                        control_key = self.key(f"control:v2:{item['execution_kind']}:{run_id}")
                        await pipe.watch(control_key)
                        control = {k: json.loads(v) for k, v in (await pipe.hgetall(control_key)).items()}
                        if (not control or control.get('revoked') or control.get('cancel_requested') or
                                control.get('status') not in ACTIVE or
                                control.get('execution_token') != item.get('execution_token')):
                            raise ValueError("执行已结束或权限已撤销，不能提交答案")
                    status = "cancelled" if item.get('kind') == 'question' and answer is None else "resolved"
                    item.update(status=status, approved=approved, reason=reason,
                                resolved_at=time.time())
                    if answer is not None:
                        item['answer'] = answer
                    pipe.multi()
                    pipe.set(key, encode(item), ex=self.retention)
                    pipe.srem(self.key(f"confirmations:{run_id}"), confirmation_id)
                    await pipe.execute()
                    return item, True
                except WatchError:
                    continue

    async def _check_local_tasks(self):
        while True:
            try:
                for identity, task in list(self._tasks.items()):
                    if identity in self._finalizing:
                        continue
                    state = await self.retry_redis(lambda: self.get_state(*identity.split(":", 1)))
                    revoked = (not state or state.get('revoked') or state.get('status') not in ACTIVE or
                               state.get('execution_token') != self._claims.get(identity) or
                               state.get('owner_worker') != self.worker_id)
                    if revoked or state.get("cancel_requested"):
                        if not task.done() and not task.cancelling():
                            task.cancel("execution_revoked" if revoked else "user_cancelled")
            except REDIS_FAILURES:
                self.redis_failed()
            except Exception:
                log.exception("Redis runtime control check failed")
            await asyncio.sleep(0.5)

    async def _pulse(self):
        while True:
            try:
                await self.retry_redis(self._heartbeat)
            except REDIS_FAILURES:
                if self.closing:
                    return
                raise
            await asyncio.sleep(self.heartbeat_interval)

    async def _reap(self):
        failures = 0
        while True:
            try:
                await self.reap_orphans()
                failures = 0
            except REDIS_FAILURES:
                self.redis_failed()
                await asyncio.sleep(self.retry_delays[min(failures, len(self.retry_delays) - 1)])
                failures += 1
            except Exception:
                log.exception("Orphan reconciliation failed worker=%s", self.worker_id)
            await asyncio.sleep(1)

    async def _probe_owner(self, snapshot):
        """Count only successful negative observations; WATCH fences heartbeats/peers."""
        owner = snapshot.get("owner_worker")
        if not owner:
            return snapshot, False
        key = self.key(f"control:v2:{snapshot['kind']}:{snapshot['target_id']}")
        worker = self.key(f"worker:{owner}")
        while True:
            async with self.redis.pipeline() as pipe:
                try:
                    await pipe.watch(key, worker)
                    raw = await pipe.hgetall(key)
                    state = {k: json.loads(v) for k, v in raw.items()}
                    if (not state or state.get('status') not in ACTIVE or
                            state.get('owner_worker') != owner):
                        return None, False
                    if state.get('revoked'):
                        return state, False
                    alive = await pipe.exists(worker)
                    health = state.get('execution_health') or {'status': 'healthy', 'failed_probes': 0}
                    if alive:
                        if health['status'] == 'healthy':
                            return state, False
                        health = {'status': 'healthy', 'failed_probes': 0}
                    else:
                        seconds, micros = await self.redis.time()
                        now = seconds + micros / 1_000_000
                        if health['status'] == 'healthy':
                            health = {'status': 'suspected', 'failed_probes': 0,
                                      'next_probe_at': now + self.probe_delays[0]}
                        elif now < health['next_probe_at']:
                            return state, False
                        else:
                            count = health['failed_probes'] + 1
                            health = {'status': 'lost' if count >= len(self.probe_delays) else 'suspected',
                                      'failed_probes': count,
                                      'next_probe_at': None if count >= len(self.probe_delays) else now + self.probe_delays[count]}
                    revoked = health['status'] == 'lost'
                    pipe.multi()
                    pipe.hset(key, mapping={'execution_health': encode(health), 'revoked': encode(revoked)})
                    await pipe.execute()
                    state.update(execution_health=health, revoked=revoked)
                    log.info('Execution health run=%s worker=%s health=%s', state.get('run_id'), owner, health)
                    return state, True
                except WatchError:
                    continue

    def redis_failed(self):
        if self.redis_available:
            log.warning("Redis unavailable; pausing execution worker=%s", self.worker_id)
        self.redis_available = False

    def redis_recovered(self):
        if not self.redis_available:
            log.info("Redis recovered worker=%s", self.worker_id)
        self.redis_available = True

    async def retry_redis(self, operation, *, revalidate=False):
        attempt = 0
        while True:
            try:
                if revalidate and attempt:
                    guard = current_execution_guard.get()
                    if guard is not None:
                        await guard()
                result = await asyncio.wait_for(operation(), self.operation_timeout)
                self.redis_recovered()
                return result
            except REDIS_FAILURES:
                self.redis_failed()
                if self.closing:
                    raise
                delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                attempt += 1
                await asyncio.sleep(delay)

    @contextmanager
    def execution_context(self, kind, target_id):
        identity = f"{kind}:{target_id}"
        guard = ExecutionLease(self, kind, target_id, self._claims.get(identity))
        binding = current_execution_guard.set(guard)
        try:
            yield
        finally:
            current_execution_guard.reset(binding)


class ExecutionLease:
    def __init__(self, runtime, kind, target_id, execution_token):
        self.runtime, self.kind, self.target_id = runtime, kind, target_id
        self.execution_token = execution_token
        self.finalizing = False

    def commit_terminal(self):
        # Only the winner of the Mongo terminal CAS may finish publishing its
        # saved result. No further model/tool work runs in this phase.
        self.finalizing = True
        self.runtime._finalizing.add(f"{self.kind}:{self.target_id}")

    async def __call__(self, *, publication=False):
        async def read():
            state = await self.runtime.get_state(self.kind, self.target_id)
            if (not state or state.get("owner_worker") != self.runtime.worker_id or
                    state.get("execution_token") != self.execution_token):
                raise ExecutionRevoked(f"Execution permission revoked: {self.target_id}")
            if publication and self.finalizing:
                return state
            if self.finalizing or state.get("revoked") or state.get("status") not in {"pending", "running"}:
                raise ExecutionRevoked(f"Execution permission revoked: {self.target_id}")
            if state.get("cancel_requested"):
                raise asyncio.CancelledError("user_cancelled")
            return state
        return await self.runtime.retry_redis(read)
