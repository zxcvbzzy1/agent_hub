"""Real Redis/Mongo checks, isolated by UUID; never flush shared databases."""
import asyncio
import json
import os
import uuid

import pytest
import pytest_asyncio
from redis.exceptions import ConnectionError

from im_backend.infra.env import load_backend_env
from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path
load_backend_env()
ensure_agent_flow_path()
from infra.runtime import RedisRuntime
from infra.db.mongodb import DocumentStore
from application.services.events import EventStreamService


@pytest_asyncio.fixture
async def journal_runtime():
    name = 'event_journal_test_' + uuid.uuid4().hex
    store = DocumentStore(os.getenv('IM_MONGO_URL', 'mongodb://localhost:27017/'), name)
    for collection in ('events', 'im_events'):
        store.ensure_index(collection, [('event_id', 1)], unique=True)
    runtime = RedisRuntime(prefix=name)
    service = EventStreamService(store, runtime)
    await runtime.redis.xgroup_create(runtime.journal.queue, runtime.journal.group, id='0-0', mkstream=True)
    try:
        yield runtime, store, service
    finally:
        await runtime.close()
        keys = [key async for key in runtime.redis.scan_iter(match=name + ':*')]
        if keys:
            await runtime.redis.delete(*keys)
        await runtime.redis.aclose()
        store._client.drop_database(name)
        store.close()


def decode(raw):
    return json.loads(next(line[6:] for line in raw.splitlines() if line.startswith('data: ')))


async def bootstrap(stream):
    events = []
    while True:
        raw = await asyncio.wait_for(anext(stream), 5)
        item = decode(raw)
        if item['name'] == 'stream.ready':
            return events, next(line[4:] for line in raw.splitlines() if line.startswith('id: '))
        if item['name'] != 'stream.reset':
            events.append(item)


@pytest.mark.asyncio
async def test_user_full_cache_resume_and_pending_visibility(journal_runtime, monkeypatch):
    rt, store, service = journal_runtime
    event = await service.publish('r', 'tool.called', {'arguments': 'body'})
    assert store.find_many('events') == []
    calls = 0
    original = rt.journal.history
    def load(*args):
        nonlocal calls
        calls += 1
        return original(*args)
    monkeypatch.setattr(rt.journal, 'history', load)
    first = service.stream('r', user_id='a')
    events, cursor = await bootstrap(first)
    await first.aclose()
    assert [e['event_id'] for e in events] == [event['event_id']]
    assert calls == 1
    assert (await service.get_event('r', event['event_id'], user_id='a'))['payload']['arguments'] == 'body'
    second = service.stream('r', user_id='a')
    assert (await bootstrap(second))[0] == events
    await second.aclose()
    resumed = service.stream('r', last_id=cursor, user_id='a', summary=True)
    assert decode(await anext(resumed))['name'] == 'stream.ready'
    later = await service.publish('r', 'tool.finished', {})
    assert decode(await anext(resumed))['event_id'] == later['event_id']
    await resumed.aclose()
    assert calls == 1
    await service.list_events('r', user_id='b')
    assert calls == 2
    assert rt.journal.cache_key('run', 'r', 'a') != rt.journal.cache_key('run', 'r', 'b')


@pytest.mark.asyncio
async def test_ack_only_after_db_and_idempotent_retry(journal_runtime, monkeypatch):
    rt, store, service = journal_runtime
    event = await service.publish('r', 'tool.called', {})
    await rt.append('run', 'r', event, durable=True)
    assert await rt.redis.xlen(rt.journal.queue) == 1
    original_eval = rt.redis.eval
    async def lost_ack(script, *args):
        if "redis.call('XACK'" in script:
            raise ConnectionError('ACK lost')
        return await original_eval(script, *args)
    monkeypatch.setattr(rt.redis, 'eval', lost_ack)
    with pytest.raises(ConnectionError):
        await rt.journal.flush_once()
    assert len(store.find_many('events')) == 1
    assert (await rt.redis.xpending(rt.journal.queue, rt.journal.group))['pending'] == 1
    monkeypatch.setattr(rt.redis, 'eval', original_eval)
    rt.journal.claim_idle_ms = 0
    assert await rt.journal.flush_once() == 1
    assert len(store.find_many('events')) == 1
    assert await rt.redis.xlen(rt.journal.queue) == 0
    assert await rt.redis.xlen(rt.event_key('run', 'r')) == 1


@pytest.mark.asyncio
async def test_partial_batch_ack_and_other_worker_recovery(journal_runtime, monkeypatch):
    rt, store, service = journal_runtime
    items = [await service.publish('r', 'tool.called', {}) for _ in range(3)]
    original = store.upsert_events
    monkeypatch.setattr(store, 'upsert_events', lambda collection, rows: original(collection, rows[:1]))
    assert await rt.journal.flush_once() == 1
    assert (await rt.redis.xpending(rt.journal.queue, rt.journal.group))['pending'] == 2
    peer = RedisRuntime(url=rt.url, prefix=rt.prefix)
    peer.journal.bind(store)
    peer.journal.claim_idle_ms = 0
    monkeypatch.setattr(store, 'upsert_events', original)
    try:
        assert await peer.journal.flush_once() == 2
        assert {e['event_id'] for e in store.find_many('events')} == {e['event_id'] for e in items}
    finally:
        await peer.redis.aclose()


@pytest.mark.asyncio
async def test_db_failure_retains_pending_without_expiry(journal_runtime, monkeypatch):
    rt, store, service = journal_runtime
    event = await service.publish('r', 'tool.called', {})
    def fail(*args):
        raise RuntimeError('database offline')
    monkeypatch.setattr(store, 'upsert_events', fail)
    assert await rt.journal.flush_once() == 0
    assert await rt.redis.ttl(rt.journal.queue) == -1
    pending = rt.journal.keys('run', 'r')[3]
    assert await rt.redis.ttl(pending) == -1
    assert json.loads(await rt.redis.hget(pending, event['event_id'])) == event
    assert (await rt.journal.stats())['pending'] == 1


@pytest.mark.asyncio
async def test_initialization_single_flight_across_workers_and_publish_during_load(journal_runtime):
    rt, store, service = journal_runtime
    peer = RedisRuntime(url=rt.url, prefix=rt.prefix)
    peer.journal.bind(store)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def history():
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return []
    one = asyncio.create_task(rt.journal.snapshot('run', 'r', history, user_id='u'))
    await entered.wait()
    two = asyncio.create_task(peer.journal.snapshot('run', 'r', history, user_id='u'))
    event = await service.publish('r', 'tool.called', {})
    # Archive removes the pending body before the loader returns. The staging
    # cache must still contain the event.
    await rt.journal.flush_once()
    release.set()
    try:
        snapshots = await asyncio.gather(one, two)
        assert calls == 1
        assert all([e['event_id'] for e in result[0]] == [event['event_id']] for result in snapshots)
    finally:
        await peer.redis.aclose()


@pytest.mark.asyncio
async def test_watermark_fields_and_legacy_high_cache_are_compatible(journal_runtime):
    rt, store, service = journal_runtime
    event = await service.publish('r', 'tool.called', {})
    meta = rt.journal.keys('run', 'r')[1]
    stream_id = await rt.redis.hget(
        rt.journal.key('run:r:dedup'), event['event_id'])
    assert await rt.redis.hget(meta, 'watermark') == stream_id
    assert await rt.redis.hget(meta, 'high') is None

    events, watermark, generation = await rt.journal.snapshot(
        'run', 'r', lambda: [], user_id='new')
    assert [item['event_id'] for item in events] == [event['event_id']]
    assert watermark == stream_id
    cache = rt.journal.cache_key('run', 'r', 'new')
    assert await rt.redis.hget(cache, '__watermark') == stream_id
    assert await rt.redis.hget(cache, '__high') is None

    # A cache produced by the previous release remains readable after deploy.
    legacy = rt.journal.cache_key('run', 'r', 'legacy')
    await rt.redis.hset(legacy, mapping={
        '__ready': '1', '__generation': generation, '__high': stream_id,
        event['event_id']: json.dumps(event),
    })
    restored, restored_watermark, _ = await rt.journal.snapshot(
        'run', 'r', lambda: pytest.fail('legacy cache should not query DB'), user_id='legacy')
    assert restored == [event]
    assert restored_watermark == stream_id


@pytest.mark.asyncio
async def test_deleted_event_cannot_be_archived_or_restored(journal_runtime):
    rt, store, service = journal_runtime
    event = await service.publish_scope('s', 'message.created', {'message_id': 'm'})
    stream = rt.stream('scope', 's', lambda: rt.journal.history('scope', 's'), user_id='u')
    _, cursor = await bootstrap(stream)
    await stream.aclose()
    assert await rt.remove_projected('s', lambda e: e['event_id'] == event['event_id']) == 1
    await rt.journal.flush_once()
    assert store.find_many('im_events') == []
    assert await rt.journal.events('scope', 's', user_id='u') == []
    resumed = rt.stream('scope', 's', lambda: [], last_id=cursor, user_id='u')
    assert decode(await anext(resumed))['name'] == 'stream.reset'
    assert decode(await anext(resumed))['name'] == 'stream.ready'
    await resumed.aclose()
    with pytest.raises(ValueError):
        await rt.append('scope', 's', event, durable=True)


@pytest.mark.asyncio
async def test_complete_history_survives_live_trim_and_cache_expiry(journal_runtime):
    rt, store, service = journal_runtime
    store.insert_one('events', {'event_id': 'old', 'run_id': 'r', 'version': 2,
                               'name': 'tool.called', 'payload': {}, 'created_at': 1})
    recent = await service.publish('r', 'tool.finished', {})
    before = await service.list_events('r', user_id='u')
    await rt.redis.delete(rt.event_key('run', 'r'))
    assert await service.list_events('r', user_id='u') == before
    await rt.redis.delete(rt.journal.cache_key('run', 'r', 'u'))
    assert [e['event_id'] for e in await service.list_events('r', user_id='u')] == ['old', recent['event_id']]


@pytest.mark.asyncio
async def test_empty_stream_resume_and_invalid_cursor(journal_runtime):
    rt, _, service = journal_runtime
    stream = service.stream('empty', user_id='u')
    events, cursor = await bootstrap(stream)
    assert events == []
    await stream.aclose()
    resumed = service.stream('empty', last_id=cursor, user_id='u')
    assert decode(await anext(resumed))['name'] == 'stream.ready'
    await resumed.aclose()
    for invalid in ('bad', '1-0', cursor.split('/')[0] + '/-1-0'):
        stream = service.stream('empty', last_id=invalid, user_id='u')
        assert decode(await anext(stream))['name'] == 'stream.reset'
        await stream.aclose()


@pytest.mark.asyncio
async def test_transient_events_not_archived_and_background_lifecycle(journal_runtime):
    rt, store, service = journal_runtime
    await service.no_store_publish('r', 'llm.delta', {'delta': 'token'})
    assert await rt.redis.xlen(rt.journal.queue) == 0
    await rt.start()
    await service.publish('r', 'llm.completed', {'content': 'answer'})
    rt.journal.wakeup.set()
    for _ in range(100):
        if store.find_many('events'):
            break
        await asyncio.sleep(.05)
    assert [e['name'] for e in store.find_many('events')] == ['llm.completed']
    await rt.journal.close()
    assert rt.journal.task is None


@pytest.mark.asyncio
async def test_database_namespaces_are_distinct(journal_runtime):
    rt, _, _ = journal_runtime
    peer = RedisRuntime(url=rt.url, prefix=rt.prefix)
    class Other:
        event_namespace = 'another-database'
    peer.journal.bind(Other())
    assert rt.journal.queue != peer.journal.queue
    assert rt.event_key('run', 'same') != peer.event_key('run', 'same')
    await peer.redis.aclose()


@pytest.mark.asyncio
async def test_delete_queue_repairs_crash_before_db_delete(journal_runtime, monkeypatch):
    rt, store, service = journal_runtime
    event = await service.publish('r', 'tool.called', {})
    await rt.journal.flush_once()
    original = store.delete_many
    def failed(*args):
        raise RuntimeError('DB deletion interrupted')
    monkeypatch.setattr(store, 'delete_many', failed)
    with pytest.raises(RuntimeError):
        await rt.journal.delete('run', 'r')
    assert store.find_many('events')
    # The Redis tombstone hides the not-yet-deleted DB document even on cold load.
    assert await service.list_events('r', user_id='new') == []
    monkeypatch.setattr(store, 'delete_many', original)
    assert await rt.journal.flush_once() == 1
    assert store.find_many('events') == []
    with pytest.raises(ValueError):
        await rt.append('run', 'r', event, durable=True)


@pytest.mark.asyncio
async def test_cache_expiry_does_not_remove_pending_and_reads_renew_ttl(journal_runtime):
    rt, store, service = journal_runtime
    rt.journal.ttl = 2
    event = await service.publish('r', 'tool.called', {})
    await service.list_events('r', user_id='a')
    cache = rt.journal.cache_key('run', 'r', 'a')
    await rt.redis.pexpire(cache, 1)
    await asyncio.sleep(.02)
    assert not await rt.redis.exists(cache)
    assert await rt.redis.xlen(rt.journal.queue) == 1
    assert (await service.list_events('r', user_id='a'))[0]['event_id'] == event['event_id']
    await rt.redis.pexpire(cache, 200)
    await service.list_events('r', user_id='a')
    assert await rt.redis.pttl(cache) > 1000
    assert store.find_many('events') == []


@pytest.mark.asyncio
async def test_generation_change_during_cache_build_cannot_reintroduce_deleted_events(journal_runtime):
    rt, store, service = journal_runtime
    event = await service.publish('r', 'tool.called', {})
    await rt.journal.flush_once()
    entered, proceed = asyncio.Event(), asyncio.Event()
    calls = 0
    async def stale_history():
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await proceed.wait()
            return [event]
        return store.find_many('events', {'run_id': 'r'})
    build = asyncio.create_task(rt.journal.snapshot('run', 'r', stale_history, user_id='u'))
    await entered.wait()
    await rt.journal.delete('run', 'r')
    proceed.set()
    assert (await build)[0] == []
    assert calls == 2


@pytest.mark.asyncio
async def test_redis_publish_failure_is_not_silently_successful(journal_runtime, monkeypatch):
    rt, store, service = journal_runtime
    async def failed(*args, **kwargs):
        raise ConnectionError('redis unavailable')
    monkeypatch.setattr(rt, 'append', failed)
    with pytest.raises(ConnectionError):
        await service.publish('r', 'tool.called', {})
    assert store.find_many('events') == []
