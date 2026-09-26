import { collectRunArtifacts, isArtifactEvent } from './runtimeEvents.js'
import { buildScopeTraces } from './scopeTraces.js'

export function buildChatItems({ messages = [], events = [], conversationId, group = false }) {
  const runIds = new Set(messages.map(message => message.run_id).filter(Boolean))
  const scopedEvents = events.filter(event => event.version === 2 && event.category === 'scope' && (
    event.conversation_id === conversationId || (!event.conversation_id && runIds.has(event.run_id))
  ))
  const artifactsByRun = group ? collectRunArtifacts(scopedEvents) : new Map()
  const messageItems = messages.map(message => ({
    key: `message-${message.message_id}`,
    kind: 'message',
    created_at: message.created_at || 0,
    message,
    run_artifacts: group && message.metadata?.source === 'planner_final'
      ? artifactsByRun.get(message.run_id) || [] : [],
  }))
  const traces = buildScopeTraces(scopedEvents).map(trace => ({
    key: trace.key, kind: 'scope-trace', created_at: trace.created_at, trace,
  }))
  // DM artifacts are already persisted in the assistant reply. Group artifacts remain visible.
  const artifacts = group ? scopedEvents.filter(isArtifactEvent).map(event => ({
    key: event.event_id, kind: 'artifact', created_at: event.created_at, event,
    artifact: event.payload?.artifact || {},
  })) : []
  return [...messageItems, ...traces, ...artifacts].sort((a, b) => a.created_at - b.created_at)
}
