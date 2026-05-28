export const runtimeEventNames = new Set([
  // 'workflow.started',
  'workflow.finished',
  'workflow.failed',
  'llm.streaming',
  'llm.completed',
  'agent.think',
  'agent.tool.reasoning',
  'agent.final',
  'agent.failed',
  'tool.called',
  'tool.succeeded',
  'tool.failed',
  'tool.retrying',
  'planner.plan.generated',
  'planner.replan.reasoning',
  'planner.final',
  'human.confirmation.requested',
  'human.confirmation.resolved',
])

export const sseEventNames = [
  'room.created',
  'room.updated',
  'message.created',
  'run.created',
  'agent.reply.pending',
  'agent.reply.finished',
  'confirmation.requested',
  'message.action',
  // 'workflow.started',
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
  'human.confirmation.requested',
  // 'human.confirmation.resolved',
  // 'workflow.finished',
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

export function eventColor(name = '') {
  if (name.includes('failed')) return 'red'
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
  if (name.includes('failed')) return 'danger'
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
  if (event.name === 'agent.final') return '最终回复'
  if (event.name === 'planner.plan.generated') return `生成计划 · ${payload.steps?.length || 0} steps`
  if (event.name === 'planner.replan.reasoning') return '重规划'
  if (event.name === 'planner.final') return 'Planner 总结'
  if (event.name.startsWith('tool.')) return payload.tool_name || event.name
  if (event.name === 'workflow.started') return '开始执行'
  if (event.name === 'workflow.finished') return '执行完成'
  if (event.name === 'workflow.failed') return '执行失败'
  return event.name
}

export function eventContent(event, agentName = (value) => value) {
  const payload = event?.payload || {}
  if (event.name === 'llm.streaming') return payload.content || '...'
  if (event.name === 'llm.completed') return payload.content || '模型调用完成'
  if (event.name === 'agent.think') return payload.think || payload.content || 'Agent 正在思考'
  if (event.name === 'agent.tool.reasoning') return payload.reasoning || payload.reason || '准备调用工具'
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
