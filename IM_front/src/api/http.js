import axios from 'axios'
import { message } from 'ant-design-vue'

export const API_BASE_URL = import.meta.env.VITE_IM_API_BASE_URL || 'http://127.0.0.1:8010'

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error?.response?.data?.detail || error?.message || '请求失败'
    message.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    return Promise.reject(error)
  },
)

export default http

