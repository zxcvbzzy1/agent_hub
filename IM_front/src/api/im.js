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
