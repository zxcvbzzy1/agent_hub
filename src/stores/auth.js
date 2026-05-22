import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'

const STORAGE_KEY = 'agent-flow-auth'

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: loadSession(),
    authApiReady: true,
    loading: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user),
  },
  actions: {
    async login(payload) {
      this.loading = true
      try {
        const response = await authApi.login(payload)
        this.user = response?.item || response?.user || { username: payload.username }
        this.authApiReady = true
      } catch {
        this.user = {
          username: payload.username || 'local-user',
          mode: 'local',
        }
        this.authApiReady = false
      } finally {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this.user))
        this.loading = false
      }
    },
    async register(payload) {
      this.loading = true
      try {
        const response = await authApi.register(payload)
        this.user = response?.item || response?.user || { username: payload.username }
        this.authApiReady = true
      } catch {
        this.user = {
          username: payload.username || 'local-user',
          mode: 'local',
        }
        this.authApiReady = false
      } finally {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this.user))
        this.loading = false
      }
    },
    logout() {
      this.user = null
      localStorage.removeItem(STORAGE_KEY)
    },
  },
})

