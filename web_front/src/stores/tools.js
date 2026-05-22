import { defineStore } from 'pinia'
import { toolsApi } from '@/api/tools'

export const useToolsStore = defineStore('tools', {
  state: () => ({
    items: [],
    loading: false,
  }),
  actions: {
    async fetchTools() {
      this.loading = true
      try {
        const response = await toolsApi.list()
        this.items = response.items || []
      } finally {
        this.loading = false
      }
    },
    async uploadTool(payload) {
      const response = await toolsApi.upload(payload)
      await this.fetchTools()
      return response.item
    },
    async deleteTool(toolId) {
      const response = await toolsApi.remove(toolId)
      await this.fetchTools()
      return response.item
    },
  },
})
