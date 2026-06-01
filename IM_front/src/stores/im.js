import { defineStore } from 'pinia'
import { API_BASE_URL } from '@/api/http'
import { imApi } from '@/api/im'
import { sseEventNames } from '@/utils/runtimeEvents'

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
    contexts: [],
    events: [],
    loading: false,
    source: null,
    tools: [],
    favorites: [],
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
        await Promise.all([this.fetchAgents(), this.fetchRooms(), this.fetchArtifacts(), this.fetchContexts()])
        if (this.groupRooms[0]) {
          await this.selectGroupRoom(this.groupRooms[0].room_id)
        } else if (this.executorAgents[0]) {
          await this.selectAgent(this.executorAgents[0].agent_id)
        }
        this.fetchTools().catch(() => {})
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
    async fetchContexts() {
      const response = await imApi.contexts()
      this.contexts = response.items || []
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
    async refreshMessages() {
      if (this.currentRoom?.type === 'group') {
        const response = await imApi.messages(this.currentRoom.room_id)
        this.messages = response.items || []
        return this.messages
      }
      if (this.currentConversation?.conversation_id) {
        const response = await imApi.conversationMessages(this.currentConversation.conversation_id)
        this.messages = response.items || []
        return this.messages
      }
      return []
    },
    mergeMessage(messageItem) {
      if (!messageItem?.message_id) return
      const index = this.messages.findIndex((item) => item.message_id === messageItem.message_id)
      if (index >= 0) {
        this.messages.splice(index, 1, { ...this.messages[index], ...messageItem })
      } else {
        this.messages.push(messageItem)
        this.messages.sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
      }
    },
    async createRoom(payload) {
      const response = await imApi.createRoom(payload)
      await this.fetchRooms()
      if (response.item.type === 'group') {
        await this.selectGroupRoom(response.item.room_id)
      }
      return response.item
    },
    async updateRoom(roomId, payload) {
      const response = await imApi.updateRoom(roomId, payload)
      await this.fetchRooms()
      if (this.currentGroupRoom?.room_id === roomId) {
        this.currentGroupRoom = response.item
        this.currentRoom = response.item
      }
      return response.item
    },
    async deleteRoom(roomId) {
      await imApi.deleteRoom(roomId)
      if (this.currentGroupRoom?.room_id === roomId) {
        this.closeStream()
        this.currentGroupRoom = null
        this.currentRoom = null
        this.messages = []
        this.events = []
        this.tasks = []
        this.mode = 'empty'
      }
      await this.fetchRooms()
      if (this.mode === 'empty') {
        if (this.groupRooms[0]) await this.selectGroupRoom(this.groupRooms[0].room_id)
        else if (this.executorAgents[0]) await this.selectAgent(this.executorAgents[0].agent_id)
      }
    },
    async createAgent(payload) {
      const response = await imApi.createAgent(payload)
      await Promise.all([this.fetchAgents(), this.fetchContexts()])
      await this.selectAgent(response.item.agent_id)
      return response.item
    },
    async deleteAgent(agentId) {
      await imApi.deleteAgent(agentId)
      if (this.currentAgentId === agentId) {
        this.closeStream()
        this.currentAgentId = ''
        this.currentConversation = null
        this.messages = []
        this.events = []
        this.conversations = []
        this.mode = 'empty'
      }
      await Promise.all([this.fetchAgents(), this.fetchRooms()])
      if (this.mode === 'empty') {
        if (this.groupRooms[0]) await this.selectGroupRoom(this.groupRooms[0].room_id)
        else if (this.executorAgents[0]) await this.selectAgent(this.executorAgents[0].agent_id)
      }
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
    async deleteConversation(conversationId) {
      await imApi.deleteConversation(conversationId)
      const agentId = this.currentAgentId
      if (this.currentConversation?.conversation_id === conversationId) {
        this.closeStream()
        this.currentConversation = null
        this.messages = []
        this.events = []
        this.mode = agentId ? 'agent' : 'empty'
      }
      await this.fetchConversations(agentId)
      if (this.currentAgentId && this.conversations[0]) {
        await this.selectConversation(this.conversations[0].conversation_id)
      }
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
      this.loadFavorites().catch(() => {})
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
      this.loadFavorites().catch(() => {})
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
        const dispatchResponse = await imApi.dispatch(this.currentRoom.room_id, {
          message_id: messageItem.message_id,
          ...options,
        })
        if (dispatchResponse.item?.type === 'confirmation') {
          this.mergeMessage(dispatchResponse.item.confirmation)
          await this.refreshMessages()
        }
        await this.fetchTasks()
      } else {
        await imApi.replyConversation(this.currentConversation.conversation_id, {
          message_id: messageItem.message_id,
          auto_start: options.auto_start ?? true,
        })
        await this.refreshMessages()
        await this.fetchConversations()
      }
      return messageItem
    },
    async dispatch(messageId, payload = {}) {
      return imApi.dispatch(this.currentGroupRoom.room_id, { message_id: messageId, ...payload })
    },
    async cancelActiveRun(runId) {
      if (!this.currentGroupRoom?.room_id || !runId) return null
      const response = await imApi.cancelRoomRun(this.currentGroupRoom.room_id, runId)
      this.messages = this.messages.map((messageItem) => (
        messageItem.run_id === runId ? { ...messageItem, status: 'cancelled' } : messageItem
      ))
      await Promise.all([this.fetchTasks(), this.refreshMessages()])
      return response.item
    },
    async cancelActiveReply(messageId) {
      if (!this.currentConversation?.conversation_id || !messageId) return null
      const response = await imApi.cancelConversationMessage(this.currentConversation.conversation_id, messageId)
      this.messages = this.messages.map((messageItem) => (
        messageItem.message_id === messageId ? { ...messageItem, status: 'cancelled' } : messageItem
      ))
      await Promise.all([this.refreshMessages(), this.fetchConversations()])
      return response.item
    },
    async recordAction(messageId, payload) {
      return imApi.action(messageId, payload)
    },
    async fetchTools() {
      if (this.tools.length) return this.tools
      const r = await imApi.toolsCatalog()
      this.tools = r.items || []
      return this.tools
    },
    async uploadAvatar(file) {
      const base64 = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = (e) => resolve(e.target.result.split(',')[1])
        reader.onerror = reject
        reader.readAsDataURL(file)
      })
      const r = await imApi.uploadArtifact({
        filename: file.name,
        content_base64: base64,
        content_type: file.type,
      })
      const artifact_id = r.item.artifact_id
      return API_BASE_URL + '/api/im/artifacts/' + artifact_id
    },
    async loadFavorites() {
      let scopeType, scopeId
      if (this.currentRoom?.type === 'group') {
        scopeType = 'room'
        scopeId = this.currentRoom.room_id
      } else if (this.currentConversation) {
        scopeType = 'conversation'
        scopeId = this.currentConversation.conversation_id
      } else {
        this.favorites = []
        return
      }
      const r = await imApi.favorites(scopeType, scopeId)
      this.favorites = r.items || []
    },
    async favoriteMessage(messageId, title = '') {
      await imApi.favoriteMessage(messageId, { title })
      await this.loadFavorites()
    },
    async removeFavorite(favoriteId) {
      await imApi.deleteFavorite(favoriteId)
      await this.loadFavorites()
    },
    async toggleConversationPinned(conversationId, pinned) {
      await imApi.updateConversation(conversationId, { pinned })
      await this.fetchConversations()
    },
    async toggleConversationArchived(conversationId, archived) {
      await imApi.updateConversation(conversationId, { archived })
      await this.fetchConversations()
    },
    async regenerateReply(agentMessage) {
      const userId = agentMessage?.metadata?.reply_to
      if (!userId || !this.currentConversation) return
      await imApi.regenerateConversationMessage(this.currentConversation.conversation_id, userId)
      await this.refreshMessages()
      await this.fetchConversations()
    },
    closeStream() {
      if (this.source) {
        this.source.close()
        this.source = null
      }
    },
    connectRoom(roomId) {
      this.connectStream(`/api/im/rooms/${roomId}/events`)
    },
    connectConversation(conversationId) {
      this.connectStream(`/api/im/conversations/${conversationId}/events`)
    },
    connectStream(path) {
      this.closeStream()
      const source = new EventSource(`${API_BASE_URL}${path}`)
      source.onmessage = (event) => this.consumeEvent(JSON.parse(event.data))
      for (const name of sseEventNames) {
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
        if (messageItem) this.mergeMessage(messageItem)
        if (this.currentRoom?.type === 'group') this.fetchTasks().catch(() => {})
        if (this.currentAgentId) this.fetchConversations().catch(() => {})
      }
      if (event.name === 'confirmation.requested' && event.payload?.confirmation) {
        this.mergeMessage(event.payload.confirmation)
      }
      if (event.name === 'message.regenerated') {
        this.refreshMessages().catch(() => {})
      }
      if (event.name === 'conversation.updated' && this.currentAgentId) {
        this.fetchConversations().catch(() => {})
      }
      if (event.name === 'favorite.created' || event.name === 'favorite.updated' || event.name === 'favorite.deleted') {
        this.loadFavorites().catch(() => {})
      }
      if (event.name === 'run.created' && this.currentRoom?.type === 'group') {
        this.fetchTasks().catch(() => {})
      }
      if (event.name === 'agent.reply.started') {
        const messageId = event.payload?.message_id
        this.messages = this.messages.map((messageItem) => (
          messageItem.message_id === messageId ? { ...messageItem, status: 'running' } : messageItem
        ))
      }
      if (event.name === 'run.cancelled') {
        const runId = event.payload?.run_id
        const messageId = event.payload?.message_id
        this.messages = this.messages.map((messageItem) => (
          messageItem.run_id === runId || messageItem.message_id === messageId
            ? { ...messageItem, status: 'cancelled' }
            : messageItem
        ))
        if (this.currentRoom?.type === 'group') this.fetchTasks().catch(() => {})
      }
      if (event.name === 'workflow.failed' && event.payload?.cancelled) {
        const runId = event.payload?.run_id
        const messageId = event.payload?.message_id
        this.messages = this.messages.map((messageItem) => (
          messageItem.run_id === runId || messageItem.message_id === messageId
            ? { ...messageItem, status: 'cancelled' }
            : messageItem
        ))
        if (this.currentRoom?.type === 'group') this.fetchTasks().catch(() => {})
        if (this.currentAgentId) this.fetchConversations().catch(() => {})
      }
    },
  },
})
