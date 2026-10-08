import test from 'node:test'
import assert from 'node:assert/strict'
import { buildComposerPlan, selectComposerRun } from './composerPlan.js'
import { PlanEventLoader } from './planEventLoader.js'

const step = (id, status = 'pending') => ({ step_id: id, title: `步骤${id}`, executor_id: 'writer', status })
const event = (name, time, payload = {}, extra = {}) => ({
  name, event_id: `${name}-${time}`, run_id: 'r1', conversation_id: 'c1', scope_id: 'room',
  category: 'scope', created_at: time, payload, ...extra,
})
const select = (events = [], tasks = [], messages = []) => selectComposerRun({ conversationId: 'c1', events, tasks, messages })
const model = events => buildComposerPlan(select(events))

test('only confirmed plan runs show generation; ordinary replies stay hidden', () => {
  assert.equal(model([event('workflow.started', 1, { mode: 'direct' })]), null)
  const run = select([], [{ run_id: 'r1', mode: 'plan', status: 'running', created_at: 1 }])
  assert.equal(buildComposerPlan(run).summary, '计划生成中')
  assert.equal(model([event('agent.execution.started', 1, { phase: 'generate_plan' })]).phase, 'generating')
})

test('generation, parallel execution, observations and replanning use current steps', () => {
  const events = [event('plan.generated', 1, { steps: [step('a'), step('b')] })]
  assert.equal(model(events).phase, 'generated')
  events.push(event('plan.step.started', 2, { step: step('a', 'in_progress') }))
  assert.match(model(events).summary, /正在步骤a/)
  events.push(event('plan.step.started', 3, { step: step('b', 'in_progress') }))
  assert.match(model(events).summary, /执行中 2 项/)
  events.push(event('plan.step.observed', 4, { step: step('a', 'done') }))
  assert.match(model(events).summary, /已完成 1\/2/)
  events.push(event('plan.step.observed', 5, { step: step('b', 'done') }))
  events.push(event('agent.execution.started', 6, { phase: 'replan_after_observation' }))
  assert.equal(model(events).phase, 'updating')
  events.push(event('plan.replanned', 7, { steps: [step('a', 'done'), step('c')] }))
  assert.equal(model(events).phase, 'updated')
  assert.deepEqual(model(events).steps.map(s => s.step_id), ['a', 'c'])
})

test('summary, completion, failure, cancellation and skipped steps remain distinct', () => {
  const start = [event('plan.generated', 1, { steps: [step('a', 'done'), step('b', 'skipped')] })]
  assert.equal(model([...start, event('agent.execution.started', 2, { phase: 'summarize_result' })]).phase, 'summarizing')
  const ended = model([...start, event('workflow.finished', 3)])
  assert.match(ended.summary, /计划已结束.*跳过 1 项/)
  assert.equal(ended.steps[1].status, 'skipped')
  assert.equal(model([...start, event('workflow.failed', 3)]).phase, 'failed')
  assert.equal(model([...start, event('workflow.failed', 3, { cancelled: true })]).phase, 'cancelled')
  assert.equal(model([...start, event('run.cancelled', 3)]).phase, 'cancelled')
  assert.match(model([event('plan.generated', 1, { steps: [step('a', 'done')] }), event('workflow.finished', 3)]).summary, /计划已完成/)
  assert.match(model([event('plan.generated', 1, { steps: [step('a', 'failed')] }), event('workflow.finished', 3)]).summary, /计划已结束.*失败 1 项/)
  assert.match(model([event('plan.generated', 1, { steps: [step('a')] }), event('workflow.finished', 3)]).summary, /未完成 1 项/)
})

test('fresh snapshots restore full instructions and cannot be rolled back by old replay', () => {
  const task = { run_id: 'r1', mode: 'plan', status: 'finished', created_at: 1, updated_at: 10,
    plan: { steps: [{ ...step('a', 'done'), instruction: '完整说明', status_reason: '已交付' }] } }
  const run = select([event('plan.generated', 2, { steps: [step('a')] })], [task])
  assert.equal(buildComposerPlan(run).steps[0].instruction, '完整说明')
  assert.equal(buildComposerPlan(run).steps[0].status, 'done')
  assert.equal(buildComposerPlan(run).phase, 'finished')
  assert.equal(buildComposerPlan(select([], [task])).phase, 'finished')
  assert.equal(buildComposerPlan(select([event('task.updated', 11, { status: 'cancelled' })], [task])).phase, 'cancelled')
})

test('latest created run wins, late old events and duplicates cannot steal selection', () => {
  const events = [event('run.created', 1), event('plan.generated', 2),
    event('run.created', 3, {}, { run_id: 'r2' }), event('workflow.finished', 99)]
  assert.equal(select(events).runId, 'r2')
  assert.equal(buildComposerPlan(select(events)), null)
  const generated = event('plan.generated', 1, { steps: [step('a')] })
  assert.equal(select([generated, generated]).events.length, 1)
  // Regeneration can reuse a message; explicit run creation is more recent.
  assert.equal(select(events, [{ run_id: 'r2', created_at: 0.5 }]).runId, 'r2')
})

test('room events cannot leak across conversations, including reused run IDs', () => {
  const wrong = event('plan.generated', 100, { steps: [step('other')] }, { conversation_id: 'c2' })
  const right = event('plan.generated', 1, { steps: [step('a')] })
  assert.deepEqual(model([right, wrong]).steps.map(s => s.step_id), ['a'])
  assert.equal(select([wrong]), null)
  assert.equal(selectComposerRun({ events: [right] }), null)
  const legacy = event('plan.generated', 1, { steps: [step('a')] }, { conversation_id: '' })
  assert.equal(select([legacy]), null)
  assert.equal(select([legacy], [], [{ run_id: 'r1', conversation_id: 'c1' }]).runId, 'r1')
})

test('scope event details hydrate compact SSE without mutating it', () => {
  const bare = event('plan.step.started', 2)
  const details = new Map([[bare.event_id, { ...bare, payload: { steps: [step('a', 'in_progress')] } }]])
  assert.equal(buildComposerPlan(select([bare]), details).steps[0].status, 'in_progress')
  assert.deepEqual(bare.payload, {})
})

const settle = () => new Promise(resolve => setImmediate(resolve))
test('detail loader deduplicates, retries failures, and ignores late responses after switch', async () => {
  let calls = 0
  let finish
  const loader = new PlanEventLoader({ api: { scopeEvent: async () => {
    calls++
    if (calls === 1) throw new Error('offline')
    return new Promise(resolve => { finish = resolve })
  } } })
  const item = event('plan.generated', 1)
  loader.load([item, item])
  await settle()
  assert.equal(calls, 1)
  assert.equal(loader.errors.size, 1)
  loader.load([item])
  await settle()
  assert.equal(calls, 1)
  loader.load([item], true)
  await settle()
  assert.equal(calls, 2)
  loader.clear()
  finish({ item })
  await settle()
  assert.equal(loader.details.size, 0)
  assert.equal(loader.pending.size, 0)
})

test('detail loader limits concurrency and caches successful details', async () => {
  const finishes = []
  const loader = new PlanEventLoader({ api: { scopeEvent: (scopeId, id) => new Promise(resolve => {
    finishes.push(() => resolve({ item: { event_id: id } }))
  }) } })
  const events = Array.from({ length: 7 }, (_, i) => event('plan.generated', i))
  loader.load(events)
  await settle()
  assert.equal(finishes.length, 4)
  finishes.splice(0).forEach(done => done())
  await settle()
  assert.equal(finishes.length, 3)
  finishes.splice(0).forEach(done => done())
  await settle()
  assert.equal(loader.details.size, 7)
  loader.load(events)
  await settle()
  assert.equal(finishes.length, 0)
})
