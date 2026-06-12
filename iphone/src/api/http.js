import axios from 'axios'

export function getApiBaseUrl() {
  const raw = localStorage.getItem('agent-im-server') || ''
  return raw.replace(/\/+$/, '')
}

function getToken() {
  try {
    const session = JSON.parse(localStorage.getItem('agent-im-auth') || 'null')
    return session?.token || ''
  } catch {
    return ''
  }
}

// 默认 axios 实例：动态 baseURL + token + 剥 response.data；401 强制跳登录
const http = axios.create()

http.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl()
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem('agent-im-auth')
      window.location.hash = '#/login'
      window.location.reload()
    }
    return Promise.reject(error)
  },
)

export default http

// 静默实例：供后台轮询使用，不做 401 跳转、不弹任何错误
export const silentHttp = axios.create()

silentHttp.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl()
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

silentHttp.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error),
)
