import { API_BASE_URL } from '@/api/http'

export function connectRunEvents(runId, handlers = {}) {
  const source = new EventSource(`${API_BASE_URL}/api/runs/${runId}/events`)
  const eventNames = [
    // 'workflow.started',
    'plan.generated',
    'wave.completed',
    'plan.replanned',
    'plan.step.observed',
    // 'plan.wave.completed',
    'workflow.finished',
    'workflow.failed',
    'tool.called',
    'tool.succeeded',
    'tool.failed',
    'tool.retrying',
    'agent.failed',
    'plan.step.failed',
    'human.confirmation.requested',
    'human.confirmation.resolved',
    'llm.started',
    'llm.delta',
    'llm.completed',
    'agent.think',
    'agent.tool.reasoning',
    'agent.final',
    'planner.plan.generated',
    'planner.replan.reasoning',
    'planner.final',
  ]

  const handleEvent = (event) => {
    const parsed = JSON.parse(event.data)
    handlers.onEvent?.(parsed)
    if (parsed.name === 'workflow.finished' || parsed.name === 'workflow.failed') {
      handlers.onDone?.(parsed)
      source.close()
    }
  }

  eventNames.forEach((name) => source.addEventListener(name, handleEvent))
  source.onerror = (event) => {
    handlers.onError?.(event)
  }
  source.onopen = () => handlers.onOpen?.()

  return {
    source,
    close: () => source.close(),
  }
}
