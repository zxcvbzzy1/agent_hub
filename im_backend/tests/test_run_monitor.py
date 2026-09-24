from __future__ import annotations

import asyncio

import pytest

from im_backend.tests.test_redis_im_integration import backend, wait_finished


@pytest.mark.asyncio
async def test_active_runs_empty_shape(backend):
    _, client, headers = backend
    response = await client.get('/api/im/runs/active', headers=headers)
    assert response.status_code == 200
    assert response.json() == {'items': [], 'recent': []}


@pytest.mark.asyncio
async def test_orchestration_run_visible_and_cancellable(backend):
    container, client, headers = backend
    runtime = container.bridge.runtime
    record = dict(run_id='monitor-run', mode='plan', prompt='long prompt ' * 50,
                  executor_agent_ids=['agent-a', 'agent-b'], planner_agent_id='default_planner',
                  status='running', plan={'big': 'x' * 1000}, final='')
    container.store.insert_one('runs', record)
    await runtime.claim('orchestration', record['run_id'], record)
    async def execute():
        try:
            await asyncio.Event().wait()
        finally:
            await container.bridge.runs._mark_run_cancelled(record, '用户中断', True)
            await container.bridge.runs.states.finish_control(record['run_id'])
    task = asyncio.create_task(execute())
    runtime.track('orchestration', record['run_id'], task)
    listed = (await client.get('/api/im/runs/active', headers=headers)).json()
    item = listed['items'][0]
    assert item['kind'] == 'orchestration'
    assert item['agent_ids'] == ['agent-a', 'agent-b']
    assert len(item['prompt']) <= 200
    assert 'plan' not in item
    response = await client.post('/api/im/runs/monitor-run/cancel', headers=headers)
    assert response.status_code == 202
    assert response.json()['cancel_requested'] is True
    assert (await wait_finished(runtime, 'orchestration', 'monitor-run'))['status'] == 'cancelled'
    listed = (await client.get('/api/im/runs/active', headers=headers)).json()
    assert listed['items'] == []
    assert listed['recent'][0]['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_lost_owner_marks_only_its_records_cancelled(backend):
    container, _, _ = backend
    runtime = container.bridge.runtime
    container.store.insert_one('runs', {'run_id':'lost-run','status':'running'})
    await runtime.put_state('orchestration', 'lost-run', {
        'run_id':'lost-run','status':'running','owner_worker':'dead-worker'})
    container.store.insert_one('im_messages', {
        'message_id':'lost-message','conversation_id':'conv','sender_type':'user','status':'running','run_id':'lost-reply'})
    container.store.insert_one('runs', {'run_id':'lost-reply', 'kind':'dm_reply', 'status':'running',
                                      'conversation_id':'conv', 'message_id':'lost-message', 'agent_id':'agent'})
    await runtime.put_state('dm_reply','lost-reply', {
        'run_id':'lost-reply','status':'running','owner_worker':'dead-worker',
        'conversation_id':'conv','agent_id':'agent'})
    await runtime.reap_orphans()
    assert container.store.find_one('runs',{'run_id':'lost-run'})['status']=='cancelled'
    assert container.store.find_one('im_messages',{'message_id':'lost-message'})['status']=='cancelled'
    assert await runtime.active_states() == []


@pytest.mark.asyncio
async def test_cancel_unknown_run_returns_404(backend):
    _, client, headers = backend
    response = await client.post('/api/im/runs/does-not-exist/cancel', headers=headers)
    assert response.status_code == 404
