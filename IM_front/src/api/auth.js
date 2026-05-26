import http from '@/api/http'

export const authApi = {
  register(payload) {
    return http.post('/api/im/auth/register', payload)
  },
  login(payload) {
    return http.post('/api/im/auth/login', payload)
  },
  me() {
    return http.get('/api/im/auth/me')
  },
  logout() {
    return http.post('/api/im/auth/logout')
  },
}

