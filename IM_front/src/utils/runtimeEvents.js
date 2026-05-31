export const runtimeEventNames = new Set([
  'workflow.started',
  'workflow.finished',
  'workflow.failed',
  'run.cancelled',
  'llm.streaming',
  'llm.completed',
  'agent.think',
  'agent.tool.reasoning',
  'agent.delta',
  'agent.final',
  'agent.failed',
  'tool.called',
  'tool.succeeded',
  'tool.failed',
  'tool.retrying',
  'planner.plan.generated',
  'planner.replan.reasoning',
  'planner.final',
  'plan.step.observed',
  'plan.step.failed',
  'plan.wave.completed',
  'wave.completed',
  'human.confirmation.requested',
  'human.confirmation.resolved',
])

export const sseEventNames = [
  'room.created',
  'room.updated',
  'message.created',
  'run.created',
  'run.cancelled',
  'agent.reply.pending',
  'agent.reply.started',
  'agent.reply.finished',
  'confirmation.requested',
  'message.action',
  'workflow.started',
  'workflow.failed',
  'llm.started',
  'llm.delta',
  'llm.completed',
  'agent.think',
  'agent.tool.reasoning',
  'agent.delta',
  'agent.final',
  'agent.failed',
  'tool.called',
  'tool.succeeded',
  'tool.failed',
  'tool.retrying',
  'planner.plan.generated',
  'planner.replan.reasoning',
  'planner.final',
  'plan.step.observed',
  'plan.step.failed',
  'plan.wave.completed',
  'wave.completed',
  'human.confirmation.requested',
  // 'human.confirmation.resolved',
  'workflow.finished',
]

export function compactLlmEvents(events) {
  const compacted = []
  const streaming = new Map()
  for (const event of events) {
    if (event.name === 'llm.delta') {
      const payload = event.payload || {}
      const key = `${payload.run_id || event.run_id || 'scope'}:${payload.agent_id || 'agent'}:${payload.call_role || 'call'}`
      const current = streaming.get(key) || {
        ...event,
        event_id: `streaming-${key}`,
        name: 'llm.streaming',
        payload: { ...payload, content: '', token_chunks: 0, streaming: true },
      }
      current.payload.content += payload.delta || ''
      current.payload.token_chunks = payload.sequence || current.payload.token_chunks + 1
      current.created_at = event.created_at
      streaming.set(key, current)
      continue
    }
    if (event.name === 'llm.started') continue
    if (event.name === 'llm.completed') {
      const payload = event.payload || {}
      const key = `${payload.run_id || event.run_id || 'scope'}:${payload.agent_id || 'agent'}:${payload.call_role || 'call'}`
      streaming.delete(key)
    }
    compacted.push(event)
  }
  compacted.push(...streaming.values())
  return compacted.sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
}

export function eventRunScope(event) {
  const payload = event?.payload || {}
  return payload.run_id || event?.run_id || payload.scope_id || payload.conversation_id || event?.scope_id || 'scope'
}

export function eventActorId(event) {
  const payload = event?.payload || {}
  if (payload.agent_id) return payload.agent_id
  if (payload.executor_id) return payload.executor_id
  if (payload.planner_id) return payload.planner_id
  if (payload.step?.executor_id) return payload.step.executor_id
  if (event?.name?.startsWith('planner.')) return payload.planner_agent_id || 'planner'
  if (event?.name?.startsWith('workflow.')) return payload.agent_id || 'workflow'
  return 'system'
}

export function isPrimaryOutputEvent(event, mode = 'group') {
  const name = event?.name || ''
  if (name.includes('failed') || name.includes('cancelled') || name.startsWith('human.confirmation')) return true
  if (mode === 'group') {
    return name === 'planner.plan.generated' || name === 'planner.replan.reasoning' || name === 'planner.final' || name === 'agent.final'
  }
  return false
}

export function isTraceEvent(event) {
  const name = event?.name || ''
  return (
    name === 'llm.streaming' ||
    name === 'llm.completed' ||
    name === 'agent.think' ||
    name === 'agent.tool.reasoning' ||
    name === 'agent.delta' ||
    name.startsWith('tool.') ||
    name === 'planner.replan.reasoning' ||
    name === 'workflow.started'
  )
}

export function isTraceBoundaryEvent(event) {
  return ['plan.step.observed', 'plan.step.failed', 'planner.plan.generated', 'planner.final', 'agent.final', 'agent.failed', 'workflow.failed'].includes(event?.name)
}

function isWorkflowTerminalEvent(event) {
  return event?.name === 'workflow.finished' || event?.name === 'workflow.failed'
}

export function traceDuration(trace) {
  const start = trace?.created_at || 0
  const end = trace?.updated_at || start
  const seconds = Math.max(0, end - start)
  if (seconds < 1) return '<1 秒'
  if (seconds < 10) return `${seconds.toFixed(1)} 秒`
  return `${Math.round(seconds)} 秒`
}

function createTrace({ key, scope, actorId, title = '运行轨迹', createdAt = 0, resolved = false, boundary = null }) {
  return {
    key,
    scope,
    actor_id: actorId,
    title,
    events: [],
    created_at: createdAt,
    updated_at: createdAt,
    latest_event: null,
    resolved,
    boundary,
    event_count: 0,
  }
}

function addTraceEvent(trace, event) {
  trace.events.push(event)
  trace.events.sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
  trace.created_at = trace.events[0]?.created_at || trace.created_at || event.created_at || 0
  trace.updated_at = trace.events[trace.events.length - 1]?.created_at || trace.updated_at || event.created_at || 0
  trace.latest_event = trace.events[trace.events.length - 1] || event
  trace.event_count = trace.events.length
}

function terminalTraceActorIds(event) {
  const payload = event?.payload || {}
  return [
    payload.agent_id,
    payload.executor_id,
    payload.planner_id,
    eventActorId(event),
    'workflow',
  ].filter((value, index, values) => value && values.indexOf(value) === index)
}

function recentUserBefore(messages, timestamp) {
  return [...messages]
    .filter((message) => message.sender_type === 'user' && (message.created_at || 0) <= timestamp)
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))[0]
}

export function buildConversationTraces({ messages = [], events = [], conversationId = '', agentId = '' }) {
  const traces = []
  const scopedEvents = events.filter((event) => {
    const payload = event.payload || {}
    return eventRunScope(event) === conversationId || payload.conversation_id === conversationId || eventRunScope(event) === 'scope'
  })

  const agentReplies = messages
    .filter((message) => message.sender_type === 'agent' && (!agentId || message.sender_id === agentId))
    .sort((a, b) => (a.created_at || 0) - (b.created_at || 0))

  for (const reply of agentReplies) {
    const replyTo = reply.metadata?.reply_to
    const userMessage = replyTo
      ? messages.find((message) => message.message_id === replyTo)
      : recentUserBefore(messages, reply.created_at || 0)
    const start = userMessage?.created_at || 0
    const end = reply.created_at || 0
    const traceEvents = scopedEvents.filter((event) => {
      const actorId = eventActorId(event)
      const ts = event.created_at || 0
      const matchesReply = replyTo && event.payload?.message_id === replyTo
      const matchesWindow = actorId === reply.sender_id && ts >= start && ts <= end
      if (isWorkflowTerminalEvent(event)) return matchesReply || matchesWindow
      return isTraceEvent(event) && matchesWindow
    })
    if (!traceEvents.length) continue
    const trace = createTrace({
      key: `conversation:${conversationId}:reply:${reply.message_id}`,
      scope: conversationId,
      actorId: reply.sender_id,
      title: '单聊回复过程',
      createdAt: traceEvents[0]?.created_at || start,
      resolved: true,
      boundary: reply,
    })
    for (const event of traceEvents) addTraceEvent(trace, event)
    trace.insert_before_message_id = reply.message_id
    traces.push(trace)
  }

  const covered = new Set(traces.flatMap((trace) => trace.events.map((event) => event.event_id)))
  const openEvents = scopedEvents.filter((event) => isTraceEvent(event) && !covered.has(event.event_id))
  const openBuckets = new Map()
  for (const event of openEvents) {
    const actorId = eventActorId(event)
    if (agentId && actorId !== agentId) continue
    const key = `conversation:${conversationId}:open:${actorId}`
    const trace = openBuckets.get(key) || createTrace({
      key,
      scope: conversationId,
      actorId,
      title: '正在回复',
      createdAt: event.created_at || 0,
      resolved: false,
    })
    addTraceEvent(trace, event)
    openBuckets.set(key, trace)
  }
  return [...traces, ...openBuckets.values()]
}

export function buildGroupTimelineItems({ messages = [], events = [] }) {
  const items = []
  const sortedEvents = [...events].sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
  const buckets = new Map()
  const consumedEventIds = new Set()

  function bucketKey(scope, actorId) {
    return `${scope}:${actorId}`
  }

  function getBucket(event, actorId = eventActorId(event)) {
    const scope = eventRunScope(event)
    const key = bucketKey(scope, actorId)
    const bucket = buckets.get(key) || createTrace({
      key: `trace:${key}:${event.created_at || Date.now()}`,
      scope,
      actorId,
      title: '运行过程',
      createdAt: event.created_at || 0,
      resolved: false,
    })
    buckets.set(key, bucket)
    return bucket
  }

  function closeBucket(scope, actorId, boundary, title) {
    const key = bucketKey(scope, actorId)
    const bucket = buckets.get(key)
    if (!bucket || !bucket.events.length) return null
    bucket.resolved = true
    bucket.boundary = boundary
    bucket.title = title || bucket.title
    bucket.updated_at = boundary.created_at || bucket.updated_at
    buckets.delete(key)
    return bucket
  }

  function closeBucketWithEvent(scope, actorId, event, title) {
    const bucket = buckets.get(bucketKey(scope, actorId))
    if (!bucket || !bucket.events.length) return null
    addTraceEvent(bucket, event)
    return closeBucket(scope, actorId, event, title)
  }

  function traceOutputAnchorTime(trace, boundary) {
    const start = trace.created_at || 0
    const boundaryAt = boundary?.created_at || 0
    const scope = trace.scope
    const actorId = trace.actor_id
    const eventAnchors = sortedEvents
      .filter((event) => {
        const name = event.name || ''
        const ts = event.created_at || 0
        return (
          eventRunScope(event) === scope &&
          eventActorId(event) === actorId &&
          ['agent.final', 'planner.plan.generated', 'planner.final'].includes(name) &&
          ts + 0.000001 >= start &&
          (!boundaryAt || ts <= boundaryAt + 0.000001)
        )
      })
      .map((event) => event.created_at || 0)
    const messageAnchors = messages
      .filter((message) => {
        const ts = message.created_at || 0
        return (
          message.sender_type === 'agent' &&
          message.sender_id === actorId &&
          message.run_id === scope &&
          ts + 0.000001 >= start
        )
      })
      .map((message) => message.created_at || 0)
    const anchors = [...eventAnchors, ...messageAnchors].filter(Boolean).sort((a, b) => a - b)
    return anchors.length ? anchors[0] - 0.0001 : start
  }

  function pushClosedTrace(trace, boundary) {
    items.push({
      key: `trace-${trace.key}-${boundary?.event_id || boundary?.created_at || trace.updated_at}`,
      kind: 'trace',
      created_at: traceOutputAnchorTime(trace, boundary),
      trace,
    })
  }

  for (const event of sortedEvents) {
    if (isWorkflowTerminalEvent(event)) {
      const scope = eventRunScope(event)
      let trace = null
      for (const actorId of terminalTraceActorIds(event)) {
        trace = closeBucketWithEvent(scope, actorId, event, eventTitle(event))
        if (trace) break
      }
      if (trace) {
        pushClosedTrace(trace, event)
      } else if (isPrimaryOutputEvent(event, 'group')) {
        items.push({
          key: `event-${event.event_id || `${event.name}-${event.created_at}`}`,
          kind: 'event',
          created_at: event.created_at || 0,
          event,
        })
      }
      consumedEventIds.add(event.event_id)
      continue
    }

    if (event.name === 'planner.replan.reasoning') {
      addTraceEvent(getBucket(event), event)
      consumedEventIds.add(event.event_id)
      items.push({
        key: `event-${event.event_id || `${event.name}-${event.created_at}`}`,
        kind: 'event',
        created_at: event.created_at || 0,
        event,
      })
      continue
    }

    if (isTraceEvent(event)) {
      addTraceEvent(getBucket(event), event)
      consumedEventIds.add(event.event_id)
      continue
    }

    if (event.name === 'plan.step.observed') {
      const step = event.payload?.step || {}
      const actorId = step.executor_id || eventActorId(event)
      const scope = eventRunScope(event)
      const trace = closeBucket(scope, actorId, event, `[${step.step_id || '-'}] ${step.title || '执行计划步骤'}`)
      if (trace) {
        trace.step = step
        pushClosedTrace(trace, event)
      }
      consumedEventIds.add(event.event_id)
      continue
    }

    if (event.name === 'planner.plan.generated' || event.name === 'planner.final') {
      const actorId = eventActorId(event)
      const trace = closeBucket(eventRunScope(event), actorId, event, event.name === 'planner.final' ? 'Planner 总结过程' : '计划生成过程')
      if (trace) {
        pushClosedTrace(trace, event)
      }
    }

    if (isPrimaryOutputEvent(event, 'group')) {
      items.push({
        key: `event-${event.event_id || `${event.name}-${event.created_at}`}`,
        kind: 'event',
        created_at: event.created_at || 0,
        event,
      })
      consumedEventIds.add(event.event_id)
    }
  }

  for (const bucket of buckets.values()) {
    if (!bucket.events.length) continue
    items.push({
      key: `trace-${bucket.key}`,
      kind: 'trace',
      created_at: bucket.created_at || 0,
      trace: bucket,
    })
  }

  const messageItems = messages.map((message) => ({
    key: `message-${message.message_id}`,
    kind: 'message',
    created_at: message.created_at || 0,
    message,
  }))

  return [...messageItems, ...items].sort((a, b) => a.created_at - b.created_at)
}

export function eventColor(name = '') {
  if (name.includes('failed') || name.includes('cancelled')) return 'red'
  if (name.includes('finished')) return 'green'
  if (name.startsWith('human.confirmation')) return 'orange'
  if (name.startsWith('llm.')) return 'cyan'
  if (name.startsWith('tool.')) return 'gold'
  if (name.startsWith('planner.')) return 'purple'
  if (name.startsWith('agent.')) return 'geekblue'
  if (name.startsWith('workflow.')) return 'blue'
  return 'default'
}

export function eventTone(name = '') {
  if (name.includes('failed') || name.includes('cancelled')) return 'danger'
  if (name.includes('finished')) return 'success'
  if (name.startsWith('human.confirmation')) return 'warning'
  if (name.startsWith('planner.')) return 'planner'
  if (name.startsWith('tool.')) return 'tool'
  if (name.startsWith('llm.')) return 'stream'
  if (name.startsWith('agent.')) return 'agent'
  return 'workflow'
}

export function eventTitle(event) {
  const payload = event?.payload || {}
  if (event.name === 'llm.streaming') return '模型输出中'
  if (event.name === 'llm.completed') return '模型输出完成'
  if (event.name === 'agent.think') return '思考'
  if (event.name === 'agent.tool.reasoning') return `工具决策${payload.tool_name ? ` · ${payload.tool_name}` : ''}`
  if (event.name === 'agent.delta') return 'Agent 输出'
  if (event.name === 'agent.final') return '最终回复'
  if (event.name === 'planner.plan.generated') return `生成计划 · ${payload.steps?.length || 0} steps`
  if (event.name === 'planner.replan.reasoning') return '重规划'
  if (event.name === 'planner.final') return 'Planner 总结'
  if (event.name.startsWith('tool.')) return payload.tool_name || event.name
  if (event.name === 'workflow.started') return '开始执行'
  if (event.name === 'workflow.finished') return '执行完成'
  if (event.name === 'workflow.failed') return '执行失败'
  if (event.name === 'run.cancelled') return '运行已中断'
  return event.name
}

export function eventContent(event, agentName = (value) => value) {
  const payload = event?.payload || {}
  if (event.name === 'llm.streaming') return payload.content || '...'
  if (event.name === 'llm.completed') return payload.content || '模型调用完成'
  if (event.name === 'agent.think') return payload.think || payload.content || 'Agent 正在思考'
  if (event.name === 'agent.tool.reasoning') return payload.reasoning || payload.reason || '准备调用工具'
  if (event.name === 'agent.delta') return payload.delta || payload.content || '...'
  if (event.name === 'agent.final') return payload.final || payload.finish_reason || 'Agent 已完成'
  if (event.name === 'planner.plan.generated') return formatPlan(payload.steps || [], agentName)
  if (event.name === 'planner.replan.reasoning') return [payload.action, payload.reason].filter(Boolean).join('\n') || 'Planner 发起重规划'
  if (event.name === 'planner.final') return payload.final || 'Planner 已总结'
  if (event.name.startsWith('tool.')) return payload.respond || payload.reason || JSON.stringify(payload.arguments || payload, null, 2)
  if (payload.error) return payload.error
  if (payload.final) return payload.final
  return JSON.stringify(payload, null, 2)
}

export function eventActor(event, agentName = (value) => value) {
  const payload = event?.payload || {}
  return payload.agent_name || agentName(payload.agent_id || payload.executor_id || payload.planner_id) || event.name
}

export function formatPlan(steps, agentName = (value) => value) {
  if (!steps.length) return '暂无计划步骤'
  return steps
    .map((step) => `${step.step_id || '-'} · ${step.title || step.instruction || '未命名步骤'}\n执行者：${agentName(step.executor_id)}`)
    .join('\n\n')
}
