import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'

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
    saveSession(payload) {
      this.session = {
        token: payload.token,
        user: payload.user,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.session))
    },
    clearSession() {
      this.session = null
      localStorage.removeItem(STORAGE_KEY)
    },
    async login(payload) {
      this.loading = true
      try {
        const response = await authApi.login(payload)
        this.saveSession(response.item)
        return response.item
      } finally {
        this.loading = false
      }
    },
    async register(payload) {
      this.loading = true
      try {
        const response = await authApi.register(payload)
        this.saveSession(response.item)
        return response.item
      } finally {
        this.loading = false
      }
    },
    async refreshMe() {
      if (!this.token) return null
      const response = await authApi.me()
      this.saveSession({ token: this.token, user: response.item })
      return response.item
    },
    async logout() {
      try {
        if (this.token) await authApi.logout()
      } finally {
        this.clearSession()
      }
    },
  },
})
