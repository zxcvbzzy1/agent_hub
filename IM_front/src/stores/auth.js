import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import { clearUserEventStreams } from '@/utils/eventStream'

const STORAGE_KEY = 'agent-im-auth'

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    session: loadSession(),
    loading: false,
  }),
  getters: {
    token: (state) => state.session?.token || '',
    user: (state) => state.session?.user || null,
    isAuthenticated: (state) => Boolean(state.session?.token),
  },
  actions: {
    async saveSession(payload) {
      const previous = this.session?.user?.user_id
      if (previous && previous !== payload.user?.user_id) await clearUserEventStreams(previous)
      this.session = {
        token: payload.token,
        user: payload.user,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.session))
    },
    async clearSession() {
      const userId = this.session?.user?.user_id
      if (userId) await clearUserEventStreams(userId)
      this.session = null
      localStorage.removeItem(STORAGE_KEY)
    },
    async login(payload) {
      this.loading = true
      try {
        const response = await authApi.login(payload)
        await this.saveSession(response.item)
        return response.item
      } finally {
        this.loading = false
      }
    },
    async register(payload) {
      this.loading = true
      try {
        const response = await authApi.register(payload)
        await this.saveSession(response.item)
        return response.item
      } finally {
        this.loading = false
      }
    },
    async refreshMe() {
      if (!this.token) return null
      const response = await authApi.me()
      await this.saveSession({ token: this.token, user: response.item })
      return response.item
    },
    async logout() {
      try {
        if (this.token) await authApi.logout()
      } finally {
        await this.clearSession()
      }
    },
  },
})
