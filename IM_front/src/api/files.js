import http from './http'

export const filesApi = {
  upload(file, onUploadProgress, signal) {
    const data = new FormData()
    data.append('file', file)
    return http.post('/api/im/files/upload', data, { timeout: 120000, onUploadProgress, signal })
  },
  list(before = '') { return http.get('/api/im/files', { params: { limit: 50, before } }) },
  remove(id) { return http.delete(`/api/im/files/${encodeURIComponent(id)}`) },
  async download(id, name) {
    const blob = await http.get(`/api/im/files/${encodeURIComponent(id)}/download`, { responseType: 'blob', timeout: 120000 })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = name || 'file'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}

export function fileSize(size) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`
  return `${(size / 1024 / 1024).toFixed(1)} MiB`
}
