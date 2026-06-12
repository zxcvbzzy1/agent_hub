import http, { silentHttp } from '@/api/http'

export const imApi = {
  agents() {
    return http.get('/api/im/agents')
  },
  rooms() {
    return http.get('/api/im/rooms')
  },
  room(roomId) {
    return http.get(`/api/im/rooms/${roomId}`)
  },
  agentConversations(agentId) {
    return http.get(`/api/im/agents/${agentId}/conversations`)
  },
  createAgentConversation(agentId, payload = {}) {
    return http.post(`/api/im/agents/${agentId}/conversations`, payload)
  },
  createRoomConversation(roomId, payload = {}) {
    return http.post(`/api/im/rooms/${roomId}/conversations`, payload)
  },
  conversation(conversationId) {
    return http.get(`/api/im/conversations/${conversationId}`)
  },
  conversationMessages(conversationId, params = {}) {
    return http.get(`/api/im/conversations/${conversationId}/messages`, { params })
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
  roomConversations(roomId) {
    return http.get('/api/im/rooms/' + roomId + '/conversations')
  },
  roomMessages(roomId, conversationId, params = {}) {
    const query = { ...params }
    if (conversationId) query.conversation_id = conversationId
    return http.get('/api/im/rooms/' + roomId + '/messages', { params: query })
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
  runEvents(runId) {
    return http.get(`/api/im/runs/${runId}/events`)
  },
  activity() {
    return http.get('/api/im/activity')
  },
  listRunConfirmations(runId) {
    return http.get(`/api/im/runs/${runId}/confirmations`)
  },
  resolveConfirmation(runId, confirmationId, payload) {
    return http.post(`/api/im/runs/${runId}/confirmations/${confirmationId}`, payload)
  },
  activeRuns() {
    return silentHttp.get('/api/im/runs/active')
  },
  cancelRun(runId) {
    return http.post(`/api/im/runs/${runId}/cancel`)
  },
}
