import http from '@/api/http'

export const runsApi = {
  list() {
    return http.get('/api/runs')
  },
  create(payload) {
    return http.post('/api/runs', payload)
  },
  get(runId) {
    return http.get(`/api/runs/${runId}`)
  },
  cancel(runId) {
    return http.post(`/api/runs/${runId}/cancel`)
  },
  confirmations(runId) {
    return http.get(`/api/runs/${runId}/confirmations`)
  },
  resolveConfirmation(runId, confirmationId, payload) {
    return http.post(`/api/runs/${runId}/confirmations/${confirmationId}`, payload)
  },
}
