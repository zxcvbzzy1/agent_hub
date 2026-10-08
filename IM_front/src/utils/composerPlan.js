const terminal = new Set(['finished', 'failed', 'cancelled'])
const planEvents = new Set([
  'plan.generated', 'plan.replanned', 'planner.plan.generated', 'planner.replan.reasoning',
  'plan.step.started', 'plan.step.observed', 'plan.step.failed', 'plan.wave.completed', 'wave.completed',
])
export const planDetailEvents = new Set([
  ...planEvents, 'workflow.started', 'workflow.finished', 'workflow.failed',
  'agent.execution.started', 'agent.execution.finished', 'agent.execution.failed',
])

export function eventRunId(event) {
  return event.run_id || event.payload?.run_id || event.payload?.run?.run_id
}

// Messages/tasks supplied by the store are already scoped. Explicitly mismatching
// conversation IDs always win over run membership (room streams contain all chats).
export function selectComposerRun({ conversationId, messages = [], tasks = [], events = [] }) {
  if (!conversationId) return null
  const belongs = item => !item.conversation_id || item.conversation_id === conversationId
  const runs = new Map()
  const ensure = id => {
    if (!runs.has(id)) runs.set(id, { runId: id, events: [], createdAt: Infinity })
    return runs.get(id)
  }
  for (const item of [...messages.filter(belongs), ...tasks.filter(belongs)]) {
    if (!item.run_id) continue
    const run = ensure(item.run_id)
    if (item.created_at) run.createdAt = Math.min(run.createdAt, item.created_at)
  }
  for (const task of tasks.filter(belongs)) {
    if (task.run_id) ensure(task.run_id).task = task
  }
  const unique = new Map()
  for (const event of events) {
    const id = eventRunId(event)
    if (!id || !belongs(event)) continue
    if (event.conversation_id !== conversationId && !runs.has(id)) continue
    unique.set(event.event_id || event, event)
  }
  for (const event of unique.values()) {
    const run = ensure(eventRunId(event))
    run.events.push(event)
    run.firstEventAt = Math.min(run.firstEventAt ?? Infinity, event.created_at || 0)
    if (event.name === 'run.created') run.startedAt = event.created_at
  }
  for (const run of runs.values()) {
    run.createdAt = run.startedAt || (Number.isFinite(run.createdAt) ? run.createdAt : run.firstEventAt || 0)
    run.events.sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
  }
  return [...runs.values()].sort((a, b) => b.createdAt - a.createdAt)[0] || null
}

export function buildComposerPlan(run, details = new Map()) {
  if (!run) return null
  const events = run.events.map(event => details.get(event.event_id) || event)
  const task = run.task
  const knownPlan = task?.mode === 'plan' || Array.isArray(task?.plan?.steps)
    || events.some(event => planEvents.has(event.name)
      || ['generate_plan', 'replan_after_observation', 'summarize_result'].includes(event.payload?.phase))
  if (!knownPlan) return null

  const timeline = [...events]
  if (task) timeline.push({ name: 'snapshot', created_at: task.updated_at || task.created_at || 0, payload: task })
  timeline.sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
  let steps = []
  let phase = 'generating'
  let status = ''
  for (const event of timeline) {
    const payload = event.payload || {}
    const incoming = payload.plan?.steps || payload.steps
    if (Array.isArray(incoming)) {
      const previous = new Map(steps.map(step => [step.step_id, step]))
      steps = incoming.map(step => ({ ...previous.get(step.step_id), ...step }))
    }
    if (payload.step?.step_id) {
      const index = steps.findIndex(step => step.step_id === payload.step.step_id)
      const step = { ...payload.step }
      if (event.name === 'plan.step.failed') step.status = 'failed'
      if (event.name === 'plan.step.started') step.status = 'in_progress'
      if (index < 0) steps.push(step)
      else steps[index] = { ...steps[index], ...step }
    }
    if (event.name === 'snapshot') {
      status = payload.status || status
      // A snapshot has no planner phase; retain a known phase during live work.
      if (steps.length && phase === 'generating') phase = 'generated'
    }
    if (['plan.generated', 'planner.plan.generated'].includes(event.name)) phase = 'generated'
    if (event.name === 'plan.replanned') phase = 'updated'
    if (event.name === 'planner.replan.reasoning' && payload.action === 'replan') phase = 'updating'
    if (event.name === 'agent.execution.started') {
      if (payload.phase === 'generate_plan') phase = 'generating'
      if (payload.phase === 'replan_after_observation') phase = 'updating'
      if (payload.phase === 'summarize_result') phase = 'summarizing'
    }
    if (event.name === 'agent.execution.finished' && payload.phase === 'replan_after_observation') phase = 'updated'
    if (event.name === 'plan.step.started') phase = 'executing'
    if (event.name === 'task.updated') status = payload.status || status
    if (event.name === 'workflow.finished') status = 'finished'
    if (event.name === 'workflow.failed') status = payload.cancelled ? 'cancelled' : 'failed'
    if (event.name === 'run.cancelled') status = 'cancelled'
  }
  const counts = Object.fromEntries(['done', 'failed', 'skipped', 'in_progress'].map(state => [
    state, steps.filter(step => step.status === state).length,
  ]))
  const active = steps.filter(step => step.status === 'in_progress')
  if (terminal.has(status)) phase = status
  else if (active.length) phase = 'executing'
  else if (phase === 'executing') phase = 'waiting'
  const labels = {
    generating: '计划生成中', generated: '计划已生成', updating: '计划更新中', updated: '计划已更新',
    executing: '计划执行中', waiting: '等待下一步骤', summarizing: '计划汇总中',
    finished: steps.some(step => step.status !== 'done') ? '计划已结束' : '计划已完成',
    failed: '计划失败', cancelled: '计划已取消',
  }
  const parts = [labels[phase]]
  if (steps.length) parts.push(`已完成 ${counts.done}/${steps.length}`)
  if (counts.failed) parts.push(`失败 ${counts.failed} 项`)
  if (counts.skipped) parts.push(`跳过 ${counts.skipped} 项`)
  if (status === 'finished') {
    const unfinished = steps.filter(step => !['done', 'failed', 'skipped'].includes(step.status)).length
    if (unfinished) parts.push(`未完成 ${unfinished} 项`)
  }
  if (!terminal.has(status) && active.length) {
    parts.push(active.length > 1 ? `执行中 ${active.length} 项` : `正在${active[0].title || active[0].step_id}`)
  }
  return { runId: run.runId, phase, steps, summary: parts.join(' · '), terminal: terminal.has(status) }
}
