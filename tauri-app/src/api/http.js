import axios from 'axios'
import { message } from 'ant-design-vue'

export const API_BASE_URL = import.meta.env.VITE_IM_API_BASE_URL || 'http://127.0.0.1:8010'

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

function attachToken(config) {
  try {
    const session = JSON.parse(localStorage.getItem('agent-im-auth') || 'null')
    if (session?.token) {
      config.headers.Authorization = `Bearer ${session.token}`
    }
  } catch {
    // Ignore malformed local sessions; the response interceptor will handle 401.
  }
  return config
}

http.interceptors.request.use(attachToken)

// 静默实例：带 token、剥 response.data，但出错不弹全局 toast。
// 给后台轮询类请求用（如运行监控），避免后端短暂不可用时刷屏报错。
export const silentHttp = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})
silentHttp.interceptors.request.use(attachToken)
silentHttp.interceptors.response.use((response) => response.data)

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error?.response?.data?.detail || error?.message || '请求失败'
    if (error?.response?.status === 401) {
      localStorage.removeItem('agent-im-auth')
      // hash 路由下用 location.hash 跳登录页，避免改写 tauri:// 协议的 pathname。
      const current = window.location.hash.replace(/^#/, '') || '/'
      if (!current.startsWith('/login')) {
        window.location.hash = `#/login?redirect=${encodeURIComponent(current)}`
        window.location.reload()
      }
    }
    message.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    return Promise.reject(error)
  },
)

export default http
