export function selectionMatches(state, revision, roomId, conversationId) {
  if (state.selectionRevision !== revision) return false
  if (roomId) {
    return state.currentRoom?.room_id === roomId
      && state.currentGroupConversation?.conversation_id === conversationId
  }
  return state.currentRoom?.type !== 'group'
    && state.currentConversation?.conversation_id === conversationId
}

export function selectedRunIds(state) {
  const conversationId = state.currentRoom?.type === 'group'
    ? state.currentGroupConversation?.conversation_id
    : state.currentConversation?.conversation_id
  if (!conversationId) return []

  const ids = new Set([
    ...(state.tasks || []).map(item => item.run_id),
    ...(state.messages || []).map(item => item.run_id),
  ].filter(Boolean))
  for (const event of state.events || []) {
    if (event.conversation_id === conversationId || (event.run_id && ids.has(event.run_id))) {
      if (event.run_id) ids.add(event.run_id)
    }
  }
  return [...ids]
}
