import http from '@/api/http'

export const contextsApi = {
  list() {
    return http.get('/api/contexts')
  },
  catalog() {
    return http.get('/api/contexts/catalog')
  },
  create(payload) {
    return http.post('/api/contexts', payload)
  },
  get(contextId) {
    return http.get(`/api/contexts/${contextId}`)
  },
  remove(contextId) {
    return http.delete(`/api/contexts/${contextId}`)
  },
}
