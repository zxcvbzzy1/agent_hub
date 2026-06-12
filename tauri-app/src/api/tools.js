import http from '@/api/http'

// 工具展示页用：列表只读，详情含 input_schema/metadata/events/config，config 可配置（目前仅 bash）。
export function listTools() {
  return http.get('/api/im/tools')
}

export function getTool(toolName) {
  return http.get(`/api/im/tools/${toolName}`)
}

export function patchToolConfig(toolName, payload) {
  return http.patch(`/api/im/tools/${toolName}/config`, payload)
}
