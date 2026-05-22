import { defineStore } from 'pinia'
import { agentsApi } from '@/api/agents'

export const useAgentsStore = defineStore('agents', {
  state: () => ({
    items: [],
    loading: false,
  }),
  actions: {
    async fetchAgents() {
      this.loading = true
      try {
        const response = await agentsApi.list()
        this.items = response.items || []
      } finally {
        this.loading = false
      }
    },
    async createAgent(payload) {
      const response = await agentsApi.create(payload)
      await this.fetchAgents()
      return response.item
    },
    async deleteAgent(agentId) {
      const response = await agentsApi.remove(agentId)
      await this.fetchAgents()
      return response.item
    },
  },
})
