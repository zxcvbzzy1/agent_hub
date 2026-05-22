import { defineStore } from 'pinia'
import { runsApi } from '@/api/runs'
import { connectRunEvents } from '@/api/sse'

export const useRunsStore = defineStore('runs', {
  state: () => ({
    current: null,
    items: [],
    eventsByRun: {},
    connections: {},
    loading: false,
  }),
  getters: {
    currentEvents: (state) => state.current ? state.eventsByRun[state.current.run_id] || [] : [],
  },
  actions: {
    async fetchRuns() {
      this.loading = true
      try {
        const response = await runsApi.list()
        this.items = response.items || []
        return this.items
      } finally {
        this.loading = false
      }
    },
    async createRun(payload) {
      this.loading = true
      try {
        const response = await runsApi.create(payload)
        this.current = response.item
        this.eventsByRun[response.item.run_id] = this.eventsByRun[response.item.run_id] || []
        await this.fetchRuns()
        if (payload.auto_start !== false) {
          this.connect(response.item.run_id)
        }
        return response.item
      } finally {
        this.loading = false
      }
    },
    async fetchRun(runId) {
      this.loading = true
      try {
        const response = await runsApi.get(runId)
        this.current = response.item
        return response.item
      } finally {
        this.loading = false
      }
    },
    async cancelRun(runId) {
      this.loading = true
      try {
        const response = await runsApi.cancel(runId)
        this.current = response.item
        this.disconnect(runId)
        return response.item
      } finally {
        this.loading = false
      }
    },
    connect(runId) {
      if (!runId || this.connections[runId]) return
      this.eventsByRun[runId] = this.eventsByRun[runId] || []
      this.connections[runId] = connectRunEvents(runId, {
        onEvent: (event) => {
          const events = this.eventsByRun[runId] || []
          if (!events.find((item) => item.event_id === event.event_id)) {
            this.eventsByRun[runId] = [...events, event]
          }
        },
        onDone: () => {
          this.disconnect(runId)
          this.fetchRun(runId).catch(() => {})
        },
        onError: () => {
          this.disconnect(runId)
        },
      })
    },
    disconnect(runId) {
      this.connections[runId]?.close()
      delete this.connections[runId]
    },
  },
})
