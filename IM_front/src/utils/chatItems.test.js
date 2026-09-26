import test from 'node:test'
import assert from 'node:assert/strict'

import { buildChatItems } from './chatItems.js'

test('group planner summary includes only the current run artifacts for bundle download', () => {
  const messages = [
    { message_id: 'summary-a', run_id: 'run-a', metadata: { source: 'planner_final' }, created_at: 10 },
    { message_id: 'ordinary-a', run_id: 'run-a', created_at: 9 },
    { message_id: 'summary-b', run_id: 'run-b', metadata: { source: 'planner_final' }, created_at: 20 },
  ]
  const artifact = (id, runId, conversationId, title, createdAt) => ({
    event_id: id, version: 2, category: 'scope', name: 'artifacts.document',
    run_id: runId, conversation_id: conversationId, created_at: createdAt,
    payload: { artifact: { type: 'document', title, content: id } },
  })
  const events = [
    artifact('a1', 'run-a', 'conversation', '报告', 1),
    artifact('a2', 'run-a', 'conversation', '数据', 2),
    artifact('b1', 'run-b', 'conversation', '方案', 3),
    artifact('other-conversation', 'run-a', 'other', '别的会话', 4),
  ]

  const items = buildChatItems({ messages, events, conversationId: 'conversation', group: true })
  const byId = new Map(items.filter(item => item.kind === 'message').map(item => [item.message.message_id, item]))

  assert.deepEqual(byId.get('summary-a').run_artifacts.map(item => item.artifact.title), ['报告', '数据'])
  assert.deepEqual(byId.get('summary-b').run_artifacts.map(item => item.artifact.title), ['方案'])
  assert.deepEqual(byId.get('ordinary-a').run_artifacts, [])
  assert.equal(items.filter(item => item.kind === 'artifact').length, 3)
})
