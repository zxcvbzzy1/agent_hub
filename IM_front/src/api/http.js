import axios from 'axios'
import { message } from 'ant-design-vue'

export const API_BASE_URL = import.meta.env.VITE_IM_API_BASE_URL || 'http://127.0.0.1:8010'

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  try {
    const session = JSON.parse(localStorage.getItem('agent-im-auth') || 'null')
    if (session?.token) {
      config.headers.Authorization = `Bearer ${session.token}`
    }
  } catch {
    // Ignore malformed local sessions; the response interceptor will handle 401.
  }
  return config
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error?.response?.data?.detail || error?.message || '请求失败'
    if (error?.response?.status === 401) {
      localStorage.removeItem('agent-im-auth')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
      }
    }
    message.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    return Promise.reject(error)
  },
)

export default http
