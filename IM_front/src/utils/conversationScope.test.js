import test from 'node:test'
import assert from 'node:assert/strict'

import { selectedRunIds, selectionMatches } from './conversationScope.js'

test('late responses cannot commit after the selected conversation changes', () => {
  const state = {
    selectionRevision: 4,
    currentRoom: { type: 'group', room_id: 'room' },
    currentGroupConversation: { conversation_id: 'new' },
  }
  assert.equal(selectionMatches(state, 3, 'room', 'old'), false)
  assert.equal(selectionMatches(state, 4, 'room', 'old'), false)
  assert.equal(selectionMatches(state, 4, 'room', 'new'), true)
})

test('confirmation lookup only includes runs belonging to the selected conversation', () => {
  const state = {
    currentRoom: { type: 'group', room_id: 'room' },
    currentGroupConversation: { conversation_id: 'new' },
    tasks: [{ run_id: 'new-task' }],
    messages: [{ run_id: 'new-message' }],
    events: [
      { run_id: 'old-run', conversation_id: 'old' },
      { run_id: 'new-event', conversation_id: 'new' },
      { run_id: 'new-task', conversation_id: '' },
      { run_id: 'unrelated', conversation_id: '' },
    ],
  }
  assert.deepEqual(new Set(selectedRunIds(state)), new Set(['new-task', 'new-message', 'new-event']))
})
