import http from '@/api/http'

const root = '/api/im/memory'
export const listMemoryBlocks = (params) => http.get(`${root}/blocks`, { params })
export const getMemoryBlock = (id) => http.get(`${root}/blocks/${encodeURIComponent(id)}`)
export const getMemorySource = (id) => http.get(`${root}/sources/${encodeURIComponent(id)}`)
export const getMemoryScopes = () => http.get(`${root}/scopes`)
export const getMemorySettings = () => http.get(`${root}/settings`)
export const saveMemorySettings = (config) => http.put(`${root}/settings`, config)
export const testMemoryRecall = (query, config) => http.post(`${root}/recall-test`, { query, config })
