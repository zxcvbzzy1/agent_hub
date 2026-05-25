import { defineStore } from 'pinia'
import { API_BASE_URL } from '@/api/http'
import { imApi } from '@/api/im'

export const useIMStore = defineStore('im', {
  state: () => ({
    agents: [],
    rooms: [],
    currentRoom: null,
    messages: [],
    events: [],
    loading: false,
    source: null,
  }),
  getters: {
    executorAgents(state) {
      return state.agents.filter((agent) => agent.agent_type === 'executor')
    },
    plannerAgents(state) {
      return state.agents.filter((agent) => agent.agent_type === 'planner')
    },
  },
  actions: {
    async bootstrap() {
      this.loading = true
      try {
        await Promise.all([this.fetchAgents(), this.fetchRooms()])
        if (this.rooms[0]) {
          await this.selectRoom(this.rooms[0].room_id)
        }
      } finally {
        this.loading = false
      }
    },
    async fetchAgents() {
      const response = await imApi.agents()
      this.agents = response.items || []
    },
    async fetchRooms() {
      const response = await imApi.rooms()
      this.rooms = response.items || []
    },
    async createRoom(payload) {
      const response = await imApi.createRoom(payload)
      await this.fetchRooms()
      await this.selectRoom(response.item.room_id)
      return response.item
    },
    async selectRoom(roomId) {
      const [roomResponse, messageResponse] = await Promise.all([
        imApi.room(roomId),
        imApi.messages(roomId),
      ])
      this.currentRoom = roomResponse.item
      this.messages = messageResponse.items || []
      this.events = []
      this.connectRoom(roomId)
    },
    async sendMessage(payload, dispatchPayload) {
      const response = await imApi.addMessage(this.currentRoom.room_id, payload)
      const messageItem = response.item
      if (dispatchPayload) {
        await imApi.dispatch(this.currentRoom.room_id, {
          message_id: messageItem.message_id,
          ...dispatchPayload,
        })
      }
      return messageItem
    },
    async dispatch(messageId, payload = {}) {
      return imApi.dispatch(this.currentRoom.room_id, { message_id: messageId, ...payload })
    },
    async recordAction(messageId, payload) {
      return imApi.action(messageId, payload)
    },
    connectRoom(roomId) {
      if (this.source) {
        this.source.close()
        this.source = null
      }
      const source = new EventSource(`${API_BASE_URL}/api/im/rooms/${roomId}/stream`)
      source.onmessage = (event) => this.consumeEvent(JSON.parse(event.data))
      const eventNames = [
        'room.created',
        'message.created',
        'run.created',
        'confirmation.requested',
        'message.action',
        'agent.delta',
        'agent.final',
        'agent.failed',
        'workflow.finished',
      ]
      for (const name of eventNames) {
        source.addEventListener(name, (event) => this.consumeEvent(JSON.parse(event.data)))
      }
      source.onerror = () => {
        source.close()
        if (this.source === source) this.source = null
      }
      this.source = source
    },
    consumeEvent(event) {
      if (!event?.event_id || this.events.some((item) => item.event_id === event.event_id)) return
      this.events.push(event)
      if (event.name === 'message.created') {
        const messageItem = event.payload?.message
        if (messageItem && !this.messages.some((item) => item.message_id === messageItem.message_id)) {
          this.messages.push(messageItem)
        }
      }
    },
  },
})
