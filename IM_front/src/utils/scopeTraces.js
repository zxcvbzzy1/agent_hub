const compareEvents = (a, b) => (a.created_at || 0) - (b.created_at || 0)
  || a.event_id.localeCompare(b.event_id)

// A business event is a row inside a trace, never a separate run card.
// Include the scope/conversation in keys so a replay cannot cross conversations.
export function buildScopeTraces(events) {
  const unique = new Map()
  for (const event of events) {
    if (event.version !== 2 || event.category !== 'scope' || !event.trace || !event.event_id) continue
    const context = JSON.stringify([event.scope_id, event.conversation_id, event.run_id])
    unique.set(`${context}:${event.event_id}`, event)
  }
  const runs = new Map()
  for (const event of [...unique.values()].sort(compareEvents)) {
    const key = JSON.stringify([event.scope_id, event.conversation_id, event.run_id || event.event_id])
    if (!runs.has(key)) runs.set(key, {
      key: `scope-trace:${key}`, run_id: event.run_id, events: [], executions: [],
      created_at: event.created_at || 0, updated_at: event.created_at || 0, event_count: 0,
    })
    const run = runs.get(key)
    run.updated_at = event.created_at || 0
    run.event_count++
    if (!event.execution_id) {
      run.events.push(event)
      continue
    }
    let execution = run.executions.find(item => item.execution_id === event.execution_id)
    if (!execution) {
      execution = {
        key: `${run.key}:execution:${event.execution_id}`, run_id: event.run_id,
        execution_id: event.execution_id, events: [], created_at: event.created_at || 0,
      }
      run.executions.push(execution)
    }
    execution.events.push(event)
    execution.agent_id ||= event.agent_id
    execution.agent_name ||= event.agent_name
  }
  return [...runs.values()]
}

// Flatten one invocation; keep multiple invocations (including repeat calls to
// the same agent) separate. Never query an entire run from a lifecycle row.
export function scopeTraceView(trace) {
  const executions = trace.executions || []
  const execution = trace.execution_id ? trace : executions.length === 1 ? executions[0] : null
  return {
    execution,
    children: executions.length > 1 ? executions : [],
    events: execution && execution !== trace
      ? [...trace.events, ...execution.events].sort(compareEvents) : trace.events,
    query: execution ? {
      event_id: execution.key, run_id: execution.run_id, execution_id: execution.execution_id,
    } : null,
  }
}
