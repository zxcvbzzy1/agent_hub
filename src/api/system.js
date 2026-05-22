import http from '@/api/http'

export const systemApi = {
  health() {
    return http.get('/health', { silent: true })
  },
}

