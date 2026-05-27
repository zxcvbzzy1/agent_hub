import http from '@/api/http'

export const imApi = {
  agents() {
    return http.get('/api/im/agents')
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
  rooms() {
    return http.get('/api/im/rooms')
  },
  createRoom(payload) {
    return http.post('/api/im/rooms', payload)
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
  addMessage(roomId, payload) {
    return http.post(`/api/im/rooms/${roomId}/messages`, payload)
  },
  dispatch(roomId, payload) {
    return http.post(`/api/im/rooms/${roomId}/dispatch`, payload)
  },
  action(messageId, payload) {
    return http.post(`/api/im/messages/${messageId}/actions`, payload)
  },
  artifacts() {
    return http.get('/api/im/artifacts')
  },
}
