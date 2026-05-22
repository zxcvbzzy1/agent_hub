import http from '@/api/http'

export const agentsApi = {
  list() {
    return http.get('/api/agents')
  },
  create(payload) {
    return http.post('/api/agents', payload)
  },
  remove(agentId) {
    return http.delete(`/api/agents/${encodeURIComponent(agentId)}`)
  },
}
