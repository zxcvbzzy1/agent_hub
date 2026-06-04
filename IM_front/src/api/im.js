import http from '@/api/http'

export const imApi = {
  agents() {
    return http.get('/api/im/agents')
  },
  contexts() {
    return http.get('/api/im/contexts')
  },
  createAgent(payload) {
    return http.post('/api/im/agents', payload)
  },
  builderChat(payload) {
    return http.post('/api/im/agents/builder/chat', payload)
  },
  deleteAgent(agentId) {
    return http.delete(`/api/im/agents/${agentId}`)
  },
  agentMessages(agentId) {
    return http.get(`/api/im/agents/${agentId}/messages`)
  },
  agentConversations(agentId) {
    return http.get(`/api/im/agents/${agentId}/conversations`)
  },
  createAgentConversation(agentId, payload) {
    return http.post(`/api/im/agents/${agentId}/conversations`, payload)
  },
  conversation(conversationId) {
    return http.get(`/api/im/conversations/${conversationId}`)
  },
  conversationMessages(conversationId) {
    return http.get(`/api/im/conversations/${conversationId}/messages`)
  },
  addConversationMessage(conversationId, payload) {
    return http.post(`/api/im/conversations/${conversationId}/messages`, payload)
  },
  replyConversation(conversationId, payload) {
    return http.post(`/api/im/conversations/${conversationId}/reply`, payload)
  },
  cancelConversationMessage(conversationId, messageId) {
    return http.post(`/api/im/conversations/${conversationId}/messages/${messageId}/cancel`)
  },
  deleteConversation(conversationId) {
    return http.delete(`/api/im/conversations/${conversationId}`)
  },
  rooms() {
    return http.get('/api/im/rooms')
  },
  createRoom(payload) {
    return http.post('/api/im/rooms', payload)
  },
  updateRoom(roomId, payload) {
    return http.patch(`/api/im/rooms/${roomId}`, payload)
  },
  deleteRoom(roomId) {
    return http.delete(`/api/im/rooms/${roomId}`)
  },
  room(roomId) {
    return http.get(`/api/im/rooms/${roomId}`)
  },
  messages(roomId) {
    return http.get(`/api/im/rooms/${roomId}/messages`)
  },
  tasks(roomId) {
    return http.get(`/api/im/rooms/${roomId}/tasks`)
  },
  roomConversations(roomId) {
    return http.get('/api/im/rooms/' + roomId + '/conversations')
  },
  createRoomConversation(roomId, payload) {
    return http.post('/api/im/rooms/' + roomId + '/conversations', payload)
  },
  roomMessages(roomId, conversationId) {
    return http.get('/api/im/rooms/' + roomId + '/messages', { params: conversationId ? { conversation_id: conversationId } : {} })
  },
  roomTasks(roomId, conversationId) {
    return http.get('/api/im/rooms/' + roomId + '/tasks', { params: conversationId ? { conversation_id: conversationId } : {} })
  },
  addMessage(roomId, payload) {
    return http.post(`/api/im/rooms/${roomId}/messages`, payload)
  },
  dispatch(roomId, payload) {
    return http.post(`/api/im/rooms/${roomId}/dispatch`, payload)
  },
  cancelRoomRun(roomId, runId) {
    return http.post(`/api/im/rooms/${roomId}/runs/${runId}/cancel`)
  },
  action(messageId, payload) {
    return http.post(`/api/im/messages/${messageId}/actions`, payload)
  },
  runEvents(runId) {
    return http.get(`/api/im/runs/${runId}/events`)
  },
  artifacts() {
    return http.get('/api/im/artifacts')
  },
  activity() {
    return http.get('/api/im/activity')
  },
  toolsCatalog() {
    return http.get('/api/im/tools')
  },
  uploadArtifact(payload) {
    return http.post('/api/im/artifacts/upload', payload)
  },
  favorites(scopeType, scopeId) {
    return http.get('/api/im/favorites', { params: { scope_type: scopeType, scope_id: scopeId } })
  },
  createFavorite(payload) {
    return http.post('/api/im/favorites', payload)
  },
  favoriteMessage(messageId, payload) {
    return http.post('/api/im/messages/' + messageId + '/favorite', payload)
  },
  updateFavorite(favoriteId, payload) {
    return http.patch('/api/im/favorites/' + favoriteId, payload)
  },
  deleteFavorite(favoriteId) {
    return http.delete('/api/im/favorites/' + favoriteId)
  },
  bundleArtifacts(payload) {
    return http.post('/api/im/artifacts/bundle', payload, { responseType: 'blob' })
  },
  updateConversation(conversationId, payload) {
    return http.patch('/api/im/conversations/' + conversationId, payload)
  },
  regenerateConversationMessage(conversationId, messageId) {
    return http.post('/api/im/conversations/' + conversationId + '/messages/' + messageId + '/regenerate', {})
  },
  listDeployments() {
    return http.get('/api/im/deployments')
  },
  stopDeployment(deploymentId) {
    return http.delete(`/api/im/deployments/${deploymentId}`)
  },
  restartDeployment(deploymentId) {
    return http.post(`/api/im/deployments/${deploymentId}/restart`)
  },
  touchDeployment(deploymentId) {
    return http.post(`/api/im/deployments/${deploymentId}/touch`)
  },
  downloadDeployment(deploymentId, dir) {
    return http.get('/api/im/deployments/' + deploymentId + '/download', { params: { dir }, responseType: 'blob' })
  },
}
