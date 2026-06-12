import http from '@/api/http'

export function listSkills() {
  return http.get('/api/im/skills')
}

export function getSkill(id) {
  return http.get(`/api/im/skills/${id}`)
}

export function createSkill(payload) {
  return http.post('/api/im/skills', payload)
}

export function updateSkill(id, payload) {
  return http.put(`/api/im/skills/${id}`, payload)
}

export function deleteSkill(id) {
  return http.delete(`/api/im/skills/${id}`)
}
