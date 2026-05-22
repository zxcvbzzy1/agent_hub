import { defineStore } from 'pinia'
import { systemApi } from '@/api/system'

export const useSystemStore = defineStore('system', {
  state: () => ({
    health: null,
    loading: false,
    error: '',
  }),
  getters: {
    online: (state) => state.health?.status === 'ok',
  },
  actions: {
    async fetchHealth() {
      this.loading = true
      this.error = ''
      try {
        this.health = await systemApi.health()
      } catch (error) {
        this.health = null
        this.error = error?.message || '后端不可用'
      } finally {
        this.loading = false
      }
    },
  },
})

