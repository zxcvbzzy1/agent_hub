"""Business/API regression coverage against isolated Mongo and Redis namespaces."""
from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx
import pytest
import pytest_asyncio

from im_backend.api import core
from im_backend.api.index import app
from im_backend.infra.storage.files import LocalFileStorage
from im_backend.domain.models import CodingAgentEvent
from domain.event import Event
from domain.state import Plan
from domain.run_context import current_run_id


@pytest_asyncio.fixture
async def backend(monkeypatch, tmp_path):
    db = 'agenthub_redis_test_' + uuid.uuid4().hex
    prefix = 'agenthub-test:' + uuid.uuid4().hex
    monkeypatch.setenv('IM_MONGO_DB', db)
    monkeypatch.setenv('REDIS_KEY_PREFIX', prefix)
    monkeypatch.setenv('IM_ARTIFACT_ROOT', str(tmp_path / 'artifacts'))
    container = core.IMContainer()
    container.files.storage = LocalFileStorage(tmp_path / 'uploads')
    monkeypatch.setattr(core, 'get_container', lambda: container)
    await container.bridge.runtime.start()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/im/auth/register', json={
            'username':'redis-user', 'email':'redis@example.com', 'password':'test-password'})
        headers = {'Authorization': 'Bearer ' + response.json()['item']['token']}
        try:
            yield container, client, headers
        finally:
            await container.bridge.runtime.close()
            r = container.bridge.runtime
            keys = [k async for k in r.redis.scan_iter(match=prefix + ':*')]
            if keys:
                await r.redis.delete(*keys)
            await r.redis.aclose()
            assert container.store._db.name == db
            container.store._client.drop_database(db)
            container.store.close()


async def post(client, path, headers, body):
    response = await client.post('/api/im' + path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()['item']


async def wait_finished(runtime, kind, target):
    for _ in range(100):
        state = await runtime.get_state(kind, target)
        if state and state['status'] not in {'pending','running'}:
            return state
        await asyncio.sleep(.05)
    pytest.fail(f'Task never finished: {kind}:{target}')


@pytest.mark.asyncio
async def test_dm_reply_artifact_history_state_and_cleanup(backend, monkeypatch):
    container, client, headers = backend
    original = container.bridge.agents.build_run_agent
    instances = []
    def build(agent_id):
        agent = original(agent_id)
        instances.append(agent)
        async def execute(prompt):
            await container.bridge.frontend_bridge.mirror_tool_event(Event('artifacts.document', {
                'agent_id': agent_id, 'artifact_type':'document',
                'artifact':{'type':'document','title':'result','content':'hello'}}))
            await container.bridge.events.no_store_publish(current_run_id.get(), 'llm.delta', {'delta':'answer'})
            agent.states['final'] = 'answer'
        agent.start_with_history = execute
        return agent
    monkeypatch.setattr(container.bridge.agents, 'build_run_agent', build)
    conv = await post(client, '/agents/default_executor/conversations', headers, {})
    cid = conv['conversation_id']
    await post(client, '/favorites', headers, {'scope_type':'conversation','scope_id':cid,'content':'remember'})
    mid = (await post(client, f'/conversations/{cid}/messages', headers,
        {'content_parts':[{'type':'text','text':'hello'}]}))['message_id']
    await post(client, f'/conversations/{cid}/reply', headers, {'message_id':mid})
    assert (await wait_finished(container.bridge.runtime, 'dm_reply', mid))['status'] == 'finished'
    response = await client.get(f'/api/im/conversations/{cid}/messages')
    messages = response.json()['items']
    assert messages[0]['status'] == 'finished'
    reply = next(m for m in messages if m['sender_type']=='agent')
    assert reply['metadata']['reply_to'] == mid
    assert any(p['type']=='artifact' for p in reply['content_parts'])
    assert container.bridge.events.list_events(cid)
    assert instances[0].states['pinned_context']
    r = await client.delete(f'/api/im/conversations/{cid}', headers=headers)
    assert r.status_code == 200, r.text
    runtime = container.bridge.runtime
    assert await runtime.get_state('dm_reply', mid) is None
    assert await runtime.redis.exists(runtime.key(f'events:scope:{cid}')) == 0
    assert container.bridge.events.list_events(cid) == []


@pytest.mark.asyncio
async def test_group_first_event_association_and_final_reply(backend, monkeypatch):
    container, client, headers = backend
    original = container.bridge.agents.build_run_agent
    first_seen = []
    async def observe(event):
        if event['name'] == 'workflow.started':
            first_seen.append(container.store.find_one('im_messages', {'run_id':event['run_id']}))
    container.bridge.events.subscribe(observe)
    def build(agent_id):
        agent = original(agent_id)
        if agent_id == 'default_planner':
            async def generate(state, executor_ids):
                return Plan(steps=[])
            async def summary(state):
                await container.bridge.events.publish(current_run_id.get(), 'planner.final',
                    {'planner_id':agent_id,'final':'group answer'})
                return 'group answer'
            agent.generate_plan = generate
            agent.summarize_result = summary
        return agent
    monkeypatch.setattr(container.bridge.agents, 'build_run_agent', build)
    room = await post(client, '/rooms', headers, {'member_agent_ids':['default_executor'],'title':'room'})
    rid = room['room_id']
    conv = await post(client, f'/rooms/{rid}/conversations', headers, {})
    message = await post(client, f'/rooms/{rid}/messages', headers,
        {'conversation_id':conv['conversation_id'],'content_parts':[{'type':'text','text':'do work'}]})
    dispatched = await post(client, f'/rooms/{rid}/dispatch', headers, {'message_id':message['message_id']})
    run_id = dispatched['run']['run_id']
    state = await wait_finished(container.bridge.runtime, 'orchestration', run_id)
    assert state['status'] == 'finished', state
    assert first_seen and first_seen[0]['message_id'] == message['message_id']
    msgs = (await client.get(f'/api/im/rooms/{rid}/messages')).json()['items']
    assert any(m['sender_type']=='agent' and m['content_parts'][0]['text']=='group answer' for m in msgs)
    tasks = (await client.get(f'/api/im/rooms/{rid}/tasks')).json()['items']
    assert tasks[0]['status'] == 'finished'
    entries = await container.bridge.runtime.redis.xrange(container.bridge.runtime.key(f'events:scope:{rid}'))
    names = [json.loads(f['event'])['name'] for _, f in entries]
    assert names.index('run.created') < names.index('workflow.started')
    assert names[-1] == 'workflow.finished'
    assert (await client.delete(f'/api/im/rooms/{rid}',headers=headers)).status_code == 200
    assert await container.bridge.runtime.get_state('orchestration', run_id) is None


@pytest.mark.asyncio
async def test_cross_worker_dm_cancel_and_monitor(backend, monkeypatch, tmp_path):
    container, client, headers = backend
    original = container.bridge.agents.build_run_agent
    entered = asyncio.Event()
    def build(agent_id):
        agent = original(agent_id)
        async def execute(prompt):
            entered.set()
            await asyncio.Event().wait()
        agent.start_with_history = execute
        return agent
    monkeypatch.setattr(container.bridge.agents,'build_run_agent',build)
    cid = (await post(client, '/agents/default_executor/conversations',headers,{}))['conversation_id']
    mid = (await post(client,f'/conversations/{cid}/messages',headers,{'content_parts':[{'type':'text','text':'wait'}]}))['message_id']
    await post(client,f'/conversations/{cid}/reply',headers,{'message_id':mid})
    await asyncio.wait_for(entered.wait(),3)
    peer = core.IMContainer()
    peer.files.storage = LocalFileStorage(tmp_path/'peer-uploads')
    await peer.bridge.runtime.start()
    monkeypatch.setattr(core,'get_container',lambda:peer)
    try:
        assert (await container.bridge.runtime.get_state('dm_reply',mid))['status']=='running'
        active = (await client.get('/api/im/runs/active',headers=headers)).json()['items']
        assert any(r['run_id']==mid for r in active)
        response = await client.post(f'/api/im/conversations/{cid}/messages/{mid}/cancel',headers=headers)
        assert response.status_code == 202, response.text
        assert response.json()['item']['cancel_requested'] is True
        state = await wait_finished(container.bridge.runtime,'dm_reply',mid)
        assert state['status']=='cancelled'
    finally:
        await peer.bridge.runtime.close()
        peer.store.close()


@pytest.mark.asyncio
async def test_coding_agent_deltas_and_artifacts_use_redis(backend, monkeypatch):
    container, client, headers = backend
    class Runner:
        async def run(self, **kwargs):
            yield CodingAgentEvent(type='agent.delta',payload={'delta':'hello\n@@ARTIFACT_BEGIN@@\n{"artifact_type":"document","document":{"title":"result","content":"body"}}\n@@ARTIFACT_END@@\n'})
            yield CodingAgentEvent(type='agent.final',payload={'final':'hello'})
    monkeypatch.setattr('im_backend.infra.coding_agents.executor_agent.runner_for_kind',lambda _:Runner())
    agent = await post(client,'/agents',headers,{'name':'coding','metadata':{'agent_kind':'codex'}})
    cid = (await post(client,f"/agents/{agent['agent_id']}/conversations",headers,{}))['conversation_id']
    mid = (await post(client,f'/conversations/{cid}/messages',headers,{'content_parts':[{'type':'text','text':'hello'}]}))['message_id']
    await post(client,f'/conversations/{cid}/reply',headers,{'message_id':mid})
    state = await wait_finished(container.bridge.runtime,'dm_reply',mid)
    assert state['status']=='finished',state
    events = container.bridge.events.list_events(cid)
    assert not any(e['name']=='agent.delta' for e in events)
    assert any(e['name']=='artifacts.document' for e in events)
    messages = (await client.get(f'/api/im/conversations/{cid}/messages')).json()['items']
    assert any(p['type']=='artifact' for m in messages for p in m['content_parts'])


@pytest.mark.asyncio
async def test_standalone_agent_flow_routes_use_shared_runtime(backend, monkeypatch):
    container, _, _ = backend
    from api.core import dependencies
    from api import index
    monkeypatch.setattr(dependencies, 'get_container', lambda: container.bridge)
    monkeypatch.setattr(index, 'get_container', lambda: container.bridge)
    # The bridge is deliberately usable as the runtime service container.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=index.app), base_url='http://test') as client:
        conversation = (await client.post('/api/conversations',json={'title':'standalone'})).json()['item']
        cid = conversation['conversation_id']
        response = await client.post(f'/api/conversations/{cid}/messages',json={'role':'user','content':'hello'})
        assert response.status_code == 200, response.text
        message = response.json()['item']
        response = await client.post('/api/runs',json={'prompt':'hello','mode':'react',
            'executor_agent_id':'default_executor','conversation_id':cid,
            'message_id':message['message_id'],'auto_start':False})
        assert response.status_code == 200, response.text
        run_id = response.json()['item']['run_id']
        assert (await client.get(f'/api/runs/{run_id}')).json()['item']['status']=='pending'
        response = await client.post(f'/api/runs/{run_id}/cancel')
        assert response.status_code == 202
        assert (await client.get(f'/api/runs/{run_id}')).json()['item']['status']=='cancelled'
        response = await client.delete(f'/api/conversations/{cid}')
        assert response.status_code==200, response.text
        assert await container.bridge.runtime.get_state('orchestration',run_id) is None


@pytest.mark.asyncio
async def test_file_deletion_publishes_after_threaded_io(backend):
    container, client, headers = backend
    cid = (await post(client,'/agents/default_executor/conversations',headers,{}))['conversation_id']
    response = await client.post('/api/im/files/upload',headers=headers,files={'file':('note.txt',b'hello','text/plain')})
    assert response.status_code==201,response.text
    file_id = response.json()['item']['file_id']
    await post(client,f'/conversations/{cid}/messages',headers,{'content_parts':[{'type':'file','file_id':file_id}]})
    response = await client.delete(f'/api/im/files/{file_id}',headers=headers)
    assert response.status_code==200,response.text
    assert container.files.get(file_id)['status']=='delete'
    records = await container.bridge.runtime.redis.xrange(container.bridge.runtime.key(f'events:scope:{cid}'))
    assert any(json.loads(f['event'])['name']=='file.deleted' for _,f in records)
