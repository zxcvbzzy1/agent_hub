import { defineStore } from 'pinia'
import { API_BASE_URL } from '@/api/http'
import { imApi } from '@/api/im'

export const useIMStore = defineStore('im', {
  state: () => ({
    agents: [],
    rooms: [],
    currentAgentId: '',
    currentConversation: null,
    currentGroupRoom: null,
    currentRoom: null,
    mode: 'empty',
    messages: [],
    conversations: [],
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
    groupRooms(state) {
      return state.rooms.filter((room) => room.type === 'group')
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
        if (this.groupRooms[0]) {
          await this.selectGroupRoom(this.groupRooms[0].room_id)
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
    async fetchConversations(agentId = this.currentAgentId) {
      if (!agentId) {
        this.conversations = []
        return []
      }
      const response = await imApi.agentConversations(agentId)
      this.conversations = response.items || []
      return this.conversations
    },
    async fetchTasks(roomId = this.currentGroupRoom?.room_id) {
      if (!roomId) {
        this.tasks = []
        return []
      }
      const response = await imApi.tasks(roomId)
      this.tasks = response.items || []
      return this.tasks
    },
    async createRoom(payload) {
      const response = await imApi.createRoom(payload)
      await this.fetchRooms()
      if (response.item.type === 'group') {
        await this.selectGroupRoom(response.item.room_id)
      }
      return response.item
    },
    async createConversation(agentId = this.currentAgentId, title = '') {
      if (!agentId) return null
      const agent = this.agents.find((item) => item.agent_id === agentId)
      const response = await imApi.createAgentConversation(agentId, {
        title: title || `${agent?.name || 'Agent'} 对话`,
        metadata: { source: 'IM_front' },
      })
      await Promise.all([this.fetchRooms(), this.fetchConversations(agentId)])
      await this.selectConversation(response.item.conversation_id)
      return response.item
    },
    async selectAgent(agentId) {
      this.currentAgentId = agentId
      this.currentConversation = null
      this.currentGroupRoom = null
      this.currentRoom = null
      this.messages = []
      this.events = []
      this.tasks = []
      this.mode = 'agent'
      this.closeStream()
      const conversations = await this.fetchConversations(agentId)
      if (conversations[0]) {
        await this.selectConversation(conversations[0].conversation_id)
      }
    },
    async selectConversation(conversationId) {
      const [conversationResponse, messageResponse] = await Promise.all([
        imApi.conversation(conversationId),
        imApi.conversationMessages(conversationId),
      ])
      this.currentConversation = conversationResponse.item
      this.currentGroupRoom = null
      this.currentRoom = null
      this.currentAgentId = conversationResponse.item.agent_id || this.currentAgentId
      this.mode = 'dm'
      this.messages = messageResponse.items || []
      this.events = []
      this.tasks = []
      this.connectConversation(conversationId)
      await this.fetchConversations(this.currentAgentId)
    },
    async selectGroupRoom(roomId) {
      const [roomResponse, messageResponse] = await Promise.all([
        imApi.room(roomId),
        imApi.messages(roomId),
      ])
      this.currentGroupRoom = roomResponse.item
      this.currentConversation = null
      this.currentRoom = roomResponse.item
      this.currentAgentId = ''
      this.mode = 'group'
      this.messages = messageResponse.items || []
      this.events = []
      this.conversations = []
      this.connectRoom(roomId)
      await this.fetchTasks(roomId)
    },
    async sendMessage(payload, options = {}) {
      if (this.mode === 'agent' && this.currentAgentId) {
        await this.createConversation(this.currentAgentId)
      }
      if (!this.currentRoom && !this.currentConversation) throw new Error('请先选择或创建会话')
      const isGroup = this.mode === 'group' && this.currentRoom
      const response = isGroup
        ? await imApi.addMessage(this.currentRoom.room_id, payload)
        : await imApi.addConversationMessage(this.currentConversation.conversation_id, payload)
      const messageItem = response.item
      if (isGroup) {
        await imApi.dispatch(this.currentRoom.room_id, {
          message_id: messageItem.message_id,
          ...options,
        })
      } else {
        await imApi.replyConversation(this.currentConversation.conversation_id, {
          message_id: messageItem.message_id,
          auto_start: options.auto_start ?? true,
        })
      }
      return messageItem
    },
    async dispatch(messageId, payload = {}) {
      return imApi.dispatch(this.currentGroupRoom.room_id, { message_id: messageId, ...payload })
    },
    async recordAction(messageId, payload) {
      return imApi.action(messageId, payload)
    },
    closeStream() {
      if (this.source) {
        this.source.close()
        this.source = null
      }
    },
    connectRoom(roomId) {
      this.connectStream(`/api/im/rooms/${roomId}/stream`)
    },
    connectConversation(conversationId) {
      this.connectStream(`/api/im/conversations/${conversationId}/stream`)
    },
    connectStream(path) {
      this.closeStream()
      const source = new EventSource(`${API_BASE_URL}${path}`)
      source.onmessage = (event) => this.consumeEvent(JSON.parse(event.data))
      const eventNames = [
        'room.created',
        'message.created',
        'run.created',
        'agent.reply.pending',
        'agent.reply.finished',
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
        if (this.currentAgentId) this.fetchConversations().catch(() => {})
      }
      if (event.name === 'run.created' && this.currentRoom?.type === 'group') {
        this.fetchTasks().catch(() => {})
      }
    },
  },
})
