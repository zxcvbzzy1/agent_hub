import { defineStore } from 'pinia'
import { API_BASE_URL } from '@/api/http'
import { imApi } from '@/api/im'

export const useIMStore = defineStore('im', {
  state: () => ({
    agents: [],
    rooms: [],
    currentRoom: null,
    currentAgentId: '',
    mode: 'empty',
    messages: [],
    agentMessages: [],
    tasks: [],
    artifacts: [],
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
    currentAgent(state) {
      return state.agents.find((agent) => agent.agent_id === state.currentAgentId) || null
    },
  },
  actions: {
    async bootstrap() {
      this.loading = true
      try {
        await Promise.all([this.fetchAgents(), this.fetchRooms(), this.fetchArtifacts()])
        if (this.rooms[0]) {
          await this.selectRoom(this.rooms[0].room_id)
        } else if (this.executorAgents[0]) {
          await this.selectAgent(this.executorAgents[0].agent_id)
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
    async fetchArtifacts() {
      const response = await imApi.artifacts()
      this.artifacts = response.items || []
    },
    async fetchTasks(roomId = this.currentRoom?.room_id) {
      if (!roomId) {
        this.tasks = []
        return []
      }
      const response = await imApi.tasks(roomId)
      this.tasks = response.items || []
      return this.tasks
    },
    async fetchAgentMessages(agentId = this.currentAgentId) {
      if (!agentId) {
        this.agentMessages = []
        return []
      }
      const response = await imApi.agentMessages(agentId)
      this.agentMessages = response.items || []
      return this.agentMessages
    },
    async createRoom(payload) {
      const response = await imApi.createRoom(payload)
      await this.fetchRooms()
      await this.selectRoom(response.item.room_id)
      return response.item
    },
    async selectAgent(agentId) {
      const existingRoom = this.rooms.find((room) => {
        return room.type === 'dm' && room.member_agent_ids?.length === 1 && room.member_agent_ids[0] === agentId
      })
      if (existingRoom) {
        await this.selectRoom(existingRoom.room_id)
        this.currentAgentId = agentId
      } else {
        this.currentAgentId = agentId
        this.currentRoom = null
        this.messages = []
        this.events = []
        this.mode = 'agent'
        if (this.source) {
          this.source.close()
          this.source = null
        }
      }
      await this.fetchAgentMessages(agentId)
    },
    async selectRoom(roomId) {
      const [roomResponse, messageResponse] = await Promise.all([
        imApi.room(roomId),
        imApi.messages(roomId),
      ])
      this.currentRoom = roomResponse.item
      this.currentAgentId =
        this.currentRoom.type === 'dm' ? this.currentRoom.member_agent_ids?.[0] || '' : ''
      this.mode = this.currentRoom.type
      this.messages = messageResponse.items || []
      this.events = []
      this.connectRoom(roomId)
      if (this.currentRoom.type === 'group') {
        await this.fetchTasks(roomId)
      } else if (this.currentAgentId) {
        await this.fetchAgentMessages(this.currentAgentId)
      }
    },
    async ensureDmRoom(agentId) {
      const existing = this.rooms.find((room) => {
        return room.type === 'dm' && room.member_agent_ids?.length === 1 && room.member_agent_ids[0] === agentId
      })
      if (existing) {
        await this.selectRoom(existing.room_id)
        return existing
      }
      const agent = this.agents.find((item) => item.agent_id === agentId)
      return this.createRoom({
        type: 'dm',
        title: agent?.name || 'Agent 单聊',
        member_agent_ids: [agentId],
        metadata: { source: 'IM_front', auto_dm: true },
      })
    },
    async sendMessage(payload, dispatchPayload) {
      if (!this.currentRoom && this.currentAgentId) {
        await this.ensureDmRoom(this.currentAgentId)
      }
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
        if (this.currentRoom?.type === 'group') this.fetchTasks().catch(() => {})
        if (this.currentAgentId) this.fetchAgentMessages().catch(() => {})
      }
      if (event.name === 'run.created' && this.currentRoom?.type === 'group') {
        this.fetchTasks().catch(() => {})
      }
    },
  },
})
