import test from 'node:test'
import assert from 'node:assert/strict'
import { buildScopeTraces, scopeTraceView } from '../src/utils/scopeTraces.js'
import { TraceClient } from '../src/utils/traceClient.js'
const scope = (id, name, extra = {}) => ({
  version: 2, category: 'scope', trace: true, scope_id: 'room', conversation_id: 'conversation',
  run_id: 'run', event_id: id, name, created_at: Number(id.replace(/\D/g, '')) || 0, ...extra,
})
const invocation = { execution_id: 'call-1', agent_id: 'writer', agent_name: '写作智能体' }
const lifecycle = [
  scope('1', 'workflow.started'),
  scope('2', 'agent.execution.started', invocation),
  scope('3', 'agent.execution.finished', invocation),
  scope('4', 'workflow.finished'),
]

test('four lifecycle events and replay duplicates produce one single-invocation card', () => {
  const traces = buildScopeTraces([...lifecycle, ...lifecycle].reverse())
  assert.equal(traces.length, 1)
  const view = scopeTraceView(traces[0])
  assert.equal(traces[0].event_count, 4)
  assert.equal(view.children.length, 0)
  assert.deepEqual(view.events.map(e => e.event_id), ['1', '2', '3', '4'])
  assert.equal(view.query.execution_id, 'call-1')
  assert.equal(view.execution.agent_name, '写作智能体')
})

test('parallel and repeated agent invocations stay separate under the same run', () => {
  const events = [...lifecycle,
    scope('5', 'agent.execution.started', { ...invocation, execution_id: 'call-2' }),
    scope('6', 'agent.execution.started', { execution_id: 'call-3', agent_id: 'reviewer' }),
    scope('7', 'agent.execution.finished', { ...invocation, execution_id: 'call-2' }),
  ]
  const [trace] = buildScopeTraces(events)
  const root = scopeTraceView(trace)
  assert.equal(root.query, null)
  assert.deepEqual(root.events.map(e => e.event_id), ['1', '4'])
  assert.equal(root.children.length, 3)
  assert.deepEqual(root.children.map(c => scopeTraceView(c).events.length), [2, 2, 1])
  assert.deepEqual(root.children.map(c => scopeTraceView(c).query.execution_id), ['call-1', 'call-2', 'call-3'])
  assert.equal(new Set(root.children.map(c => c.key)).size, 3)
})

test('stable run and execution keys survive status updates and regrouping', () => {
  const [pending] = buildScopeTraces(lifecycle.slice(0, 1))
  const [running] = buildScopeTraces(lifecycle.slice(0, 2))
  const [finished] = buildScopeTraces(lifecycle)
  const [multiple] = buildScopeTraces([...lifecycle, scope('5', 'agent.execution.started', { execution_id: 'call-2' })])
  assert.equal(pending.key, running.key)
  assert.equal(running.key, finished.key)
  assert.equal(finished.key, multiple.key)
  assert.equal(scopeTraceView(running).query.event_id, scopeTraceView(finished).query.event_id)
  assert.equal(scopeTraceView(running).query.event_id, scopeTraceView(multiple.executions[0]).query.event_id)
})

test('regenerations, conversations, standalone events and old history do not mix', () => {
  const traces = buildScopeTraces([
    ...lifecycle,
    scope('2', 'agent.execution.started', { ...invocation, run_id: 'retry' }),
    scope('2', 'agent.execution.started', { ...invocation, conversation_id: 'other' }),
    scope('5', 'task.updated', { run_id: '' }),
    scope('6', 'task.updated', { run_id: '' }),
    scope('7', 'agent.execution.started', { version: 1 }),
    scope('8', 'agent.think', { category: 'run' }),
    scope('9', 'artifacts.message', { trace: false }),
  ])
  assert.equal(traces.length, 5)
  assert.equal(traces.reduce((n, trace) => n + trace.event_count, 0), 8)
  assert.equal(new Set(traces.map(trace => trace.key)).size, 5)
})

test('grouped execution views request distinct summaries but share one stream', async () => {
  const calls = [], streams = []
  const client = new TraceClient({
    api: { runSummaries: async (run, params) => {
      calls.push([run, params.execution_id])
      return { items: [{ event_id: params.execution_id, execution_id: params.execution_id, created_at: 1 }], next_cursor: null }
    } },
    eventNames: [],
    openStream: () => { const stream = { addEventListener() {}, close() { this.closed = true } }; streams.push(stream); return stream },
  })
  const [trace] = buildScopeTraces([...lifecycle, scope('5', 'agent.execution.started', { execution_id: 'call-2' })])
  assert.equal(scopeTraceView(trace).query, null)
  assert.equal(calls.length, 0)
  const queries = trace.executions.map(c => scopeTraceView(c).query)
  await Promise.all(queries.map(q => client.expand(q)))
  assert.deepEqual(calls, [['run', 'call-1'], ['run', 'call-2']])
  assert.equal(streams.length, 1)
  assert.deepEqual(client.state(queries[0]).items.map(e => e.execution_id), ['call-1'])
  client.collapse(queries[0])
  assert.ok(!streams[0].closed)
  client.collapse(queries[1])
  assert.equal(streams[0].closed, true)
})
