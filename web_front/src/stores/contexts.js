import { defineStore } from 'pinia'
import { contextsApi } from '@/api/contexts'

export const useContextsStore = defineStore('contexts', {
  state: () => ({
    current: null,
    items: [],
    catalogData: null,
    loading: false,
  }),
  actions: {
    async fetchContexts() {
      this.loading = true
      try {
        const response = await contextsApi.list()
        this.items = response.items
        return response.items
      } finally {
        this.loading = false
      }
    },
    async fetchCatalog() {
      const response = await contextsApi.catalog()
      this.catalogData = response.item
      return response.item
    },
    async createContext(payload) {
      this.loading = true
      try {
        const response = await contextsApi.create(payload)
        this.current = response.item
        await this.fetchContexts()
        return response.item
      } finally {
        this.loading = false
      }
    },
    async getContext(contextId) {
      this.loading = true
      try {
        const response = await contextsApi.get(contextId)
        this.current = response.item
        return response.item
      } finally {
        this.loading = false
      }
    },
    async deleteContext(contextId) {
      this.loading = true
      try {
        const response = await contextsApi.remove(contextId)
        if (this.current?.context_id === contextId) {
          this.current = null
        }
        await this.fetchContexts()
        return response.item
      } finally {
        this.loading = false
      }
    },
  },
})
