import http from '@/api/http'

export const authApi = {
  login(payload) {
    return http.post('/api/auth/login', payload, { silent: true })
  },
  register(payload) {
    return http.post('/api/auth/register', payload, { silent: true })
  },
}

