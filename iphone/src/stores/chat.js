import { defineStore } from 'pinia'
import { imApi } from '@/api/im'
import { getApiBaseUrl } from '@/api/http'
import { sseEventNames } from '@/utils/runtimeEvents'

// 移动端聊天 store：IM_front im store 的精简版。
// 砍掉：技能/工具/收藏/任务面板/重生成等桌面能力；保留：会话、消息窗口、SSE 流、
// 发送/中断、人工确认（审批）、运行监控、未读。
const MESSAGE_PAGE_SIZE = 30
const HIGH_FREQUENCY_EVENTS = new Set(['llm.delta', 'agent.delta'])

let seenEventIds = new Set()
let pendingEvents = []
let flushHandle = null

function resetStreamState() {
  if (flushHandle !== null) {
    clearTimeout(flushHandle)
    flushHandle = null
  }
  seenEventIds = new Set()
  pendingEvents = []
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    agents: [],
    rooms: [],
    activity: [],

    // 当前聊天上下文
    chatType: '', // 'dm' | 'group'
    conversation: null, // dm: im_conversations 记录
    room: null, // group: room 记录
    groupConversationId: '',

    messages: [],
    hasMoreMessages: false,
    loadingOlder: false,
    events: [],
    source: null,
    sending: false,

    // 审批与运行
    humanConfirmations: [], // 当前聊天 SSE 推来的待审批
    pendingApprovals: [], // 审批中心聚合的全局待审批
    activeRuns: [],
    recentRuns: [],

    lastSeenCount: (() => {
      try {
        return JSON.parse(localStorage.getItem('im-mobile-lastseen-v1')) || {}
      } catch {
        return {}
      }
    })(),
  }),

  getters: {
    executorAgents(state) {
      return state.agents.filter((agent) => agent.agent_type === 'executor')
    },
    agentById(state) {
      const map = {}
      for (const agent of state.agents) map[agent.agent_id] = agent
      return map
    },
    unreadForConversation(state) {
      return (conversationId) => {
        const entry = state.activity.find((item) => item.conversation_id === conversationId)
        if (!entry) return 0
        const seen = state.lastSeenCount[conversationId] || 0
        return Math.max(0, (entry.message_count || 0) - seen)
      }
    },
    totalUnread(state) {
      let total = 0
      for (const entry of state.activity) {
        const seen = state.lastSeenCount[entry.conversation_id] || 0
        total += Math.max(0, (entry.message_count || 0) - seen)
      }
      return total
    },
    // 首页两级导航用：按智能体/群聚合未读与运行态
    unreadForAgent(state) {
      return (agentId) => {
        let total = 0
        for (const entry of state.activity) {
          if (entry.agent_id !== agentId || entry.room_id) continue
          const seen = state.lastSeenCount[entry.conversation_id] || 0
          total += Math.max(0, (entry.message_count || 0) - seen)
        }
        return total
      }
    },
    unreadForRoom(state) {
      return (roomId) => {
        let total = 0
        for (const entry of state.activity) {
          if (entry.room_id !== roomId) continue
          const seen = state.lastSeenCount[entry.conversation_id] || 0
          total += Math.max(0, (entry.message_count || 0) - seen)
        }
        return total
      }
    },
    runningAgentIds(state) {
      const ids = new Set()
      for (const run of state.activeRuns) {
        for (const agentId of run.agent_ids || []) ids.add(agentId)
      }
      return ids
    },
    runningRoomIds(state) {
      return new Set(state.activeRuns.map((run) => run.room_id).filter(Boolean))
    },
    runningConversationIds(state) {
      return new Set(state.activeRuns.map((run) => run.conversation_id).filter(Boolean))
    },
    pendingApprovalCount(state) {
      // 聊天内实时推送与审批中心聚合可能重叠，按 confirmation_id 去重计数
      const ids = new Set()
      for (const item of state.humanConfirmations) ids.add(item.confirmation_id)
      for (const item of state.pendingApprovals) ids.add(item.confirmation_id)
      return ids.size
    },
    runningCount(state) {
      return state.activeRuns.length
    },
  },

  actions: {
    // ── 基础数据 ─────────────────────────────────────────
    async bootstrap() {
      await Promise.all([this.fetchAgents(), this.fetchRooms(), this.fetchActivity()])
    },
    async fetchAgents() {
      const response = await imApi.agents()
      this.agents = response.items || []
    },
    async fetchRooms() {
      const response = await imApi.rooms()
      this.rooms = (response.items || []).filter((room) => room.type === 'group')
    },
    async fetchActivity() {
      const response = await imApi.activity()
      this.activity = response.items || []
    },
    markSeen(conversationId) {
      if (!conversationId) return
      const entry = this.activity.find((item) => item.conversation_id === conversationId)
      const total = entry?.message_count ?? this.messages.length
      this.lastSeenCount = { ...this.lastSeenCount, [conversationId]: total }
      try {
        localStorage.setItem('im-mobile-lastseen-v1', JSON.stringify(this.lastSeenCount))
      } catch {
        // 存不进就算了，下次进会话还会重算
      }
    },

    // ── 打开聊天 ─────────────────────────────────────────
    async openDm(conversationId) {
      this.closeChat()
      this.chatType = 'dm'
      const response = await imApi.conversation(conversationId)
      this.conversation = response.item
      await this.loadLatestMessages()
      this.connectStream(`/api/im/conversations/${conversationId}/events`)
      this.markSeen(conversationId)
    },
    async openGroup(roomId, conversationId = '') {
      this.closeChat()
      this.chatType = 'group'
      const response = await imApi.room(roomId)
      this.room = response.item
      if (!conversationId) {
        const list = await imApi.roomConversations(roomId)
        const first = (list.items || [])[0]
        conversationId = first?.conversation_id || ''
      }
      this.groupConversationId = conversationId
      await this.loadLatestMessages()
      this.connectStream(`/api/im/rooms/${roomId}/events`)
      if (conversationId) this.markSeen(conversationId)
    },
    closeChat() {
      if (this.source) {
        this.source.close()
        this.source = null
      }
      resetStreamState()
      this.chatType = ''
      this.conversation = null
      this.room = null
      this.groupConversationId = ''
      this.messages = []
      this.events = []
      this.hasMoreMessages = false
      this.humanConfirmations = []
    },

    // ── 消息窗口 ─────────────────────────────────────────
    async loadLatestMessages() {
      const response = await this._fetchWindow({ limit: MESSAGE_PAGE_SIZE })
      this.messages = response.items || []
      this.hasMoreMessages = Boolean(response.has_more ?? (this.messages.length >= MESSAGE_PAGE_SIZE))
    },
    async refreshMessages() {
      const response = await this._fetchWindow({ limit: MESSAGE_PAGE_SIZE })
      const list = response.items || []
      const oldestRecent = list.length ? list[0].created_at || 0 : Infinity
      const recentIds = new Set(list.map((item) => item.message_id))
      const olderKept = this.messages.filter(
        (item) => (item.created_at || 0) < oldestRecent && !recentIds.has(item.message_id),
      )
      this.messages = [...olderKept, ...list]
    },
    async loadOlderMessages() {
      if (this.loadingOlder || !this.hasMoreMessages) return 0
      const oldest = this.messages[0]
      if (!oldest?.message_id) return 0
      this.loadingOlder = true
      try {
        const response = await this._fetchWindow({ limit: MESSAGE_PAGE_SIZE, before_id: oldest.message_id })
        const items = response.items || []
        if (!items.length) {
          this.hasMoreMessages = false
          return 0
        }
        const existing = new Set(this.messages.map((item) => item.message_id))
        const fresh = items.filter((item) => !existing.has(item.message_id))
        this.messages = [...fresh, ...this.messages]
        this.hasMoreMessages = Boolean(response.has_more ?? items.length >= MESSAGE_PAGE_SIZE)
        return fresh.length
      } finally {
        this.loadingOlder = false
      }
    },
    _fetchWindow(params) {
      if (this.chatType === 'group' && this.room) {
        return imApi.roomMessages(this.room.room_id, this.groupConversationId, params)
      }
      if (this.conversation) {
        return imApi.conversationMessages(this.conversation.conversation_id, params)
      }
      return Promise.resolve({ items: [] })
    },
    mergeMessage(messageItem) {
      if (!messageItem?.message_id) return
      const index = this.messages.findIndex((item) => item.message_id === messageItem.message_id)
      if (index >= 0) {
        this.messages.splice(index, 1, { ...this.messages[index], ...messageItem })
      } else {
        this.messages.push(messageItem)
      }
    },

    // ── 发送 / 中断 ──────────────────────────────────────
    async sendText(text, mentions = []) {
      const payload = {
        sender_type: 'user',
        content_parts: [{ type: 'text', text }],
        mentions,
        metadata: { client: 'agenthub-mobile' },
      }
      this.sending = true
      try {
        if (this.chatType === 'group' && this.room) {
          const response = await imApi.addMessage(this.room.room_id, {
            ...payload,
            conversation_id: this.groupConversationId,
          })
          await imApi.dispatch(this.room.room_id, { message_id: response.item.message_id, auto_start: true })
        } else if (this.conversation) {
          const response = await imApi.addConversationMessage(this.conversation.conversation_id, payload)
          await imApi.replyConversation(this.conversation.conversation_id, {
            message_id: response.item.message_id,
            auto_start: true,
          })
        }
        await this.refreshMessages()
      } finally {
        this.sending = false
      }
    },
    async cancelDmReply(messageId) {
      if (!this.conversation) return
      await imApi.cancelConversationMessage(this.conversation.conversation_id, messageId)
      this.messages = this.messages.map((item) =>
        item.message_id === messageId ? { ...item, status: 'cancelled' } : item,
      )
      await this.refreshMessages()
    },
    async cancelGroupRun(runId) {
      if (!this.room) return
      await imApi.cancelRoomRun(this.room.room_id, runId)
    },
    async cancelAnyRun(runId) {
      await imApi.cancelRun(runId)
      await this.fetchActiveRuns().catch(() => {})
    },

    // ── 审批 ─────────────────────────────────────────────
    async resolveConfirmation(runId, confirmationId, approved, reason = '') {
      this.humanConfirmations = this.humanConfirmations.filter((c) => c.confirmation_id !== confirmationId)
      this.pendingApprovals = this.pendingApprovals.filter((c) => c.confirmation_id !== confirmationId)
      return imApi.resolveConfirmation(runId, confirmationId, { approved, reason })
    },
    async fetchPendingApprovals() {
      // 全局审批聚合：先拿活跃 run，再逐个查 pending 确认（个人规模下量很小）。
      await this.fetchActiveRuns().catch(() => {})
      const results = []
      for (const run of this.activeRuns) {
        try {
          const response = await imApi.listRunConfirmations(run.run_id)
          for (const item of response.items || []) {
            results.push({ ...item, run })
          }
        } catch {
          // 单个 run 查询失败不影响整体
        }
      }
      this.pendingApprovals = results
      return results
    },

    // ── 运行监控 ─────────────────────────────────────────
    async fetchActiveRuns() {
      const response = await imApi.activeRuns()
      this.activeRuns = response.items || []
      this.recentRuns = response.recent || []
      return this.activeRuns
    },

    // ── SSE ──────────────────────────────────────────────
    connectStream(path) {
      const source = new EventSource(`${getApiBaseUrl()}${path}`)
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
    flushPendingEvents() {
      if (flushHandle !== null) {
        clearTimeout(flushHandle)
        flushHandle = null
      }
      if (!pendingEvents.length) return
      const batch = pendingEvents
      pendingEvents = []
      this.events = this.events.concat(batch)
    },
    consumeEvent(event) {
      if (!event?.event_id || seenEventIds.has(event.event_id)) return
      seenEventIds.add(event.event_id)

      // 高频流式增量合批落库（80ms 窗口），避免逐 token 重渲染卡死手机端。
      if (HIGH_FREQUENCY_EVENTS.has(event.name)) {
        pendingEvents.push(event)
        if (flushHandle === null) {
          flushHandle = setTimeout(() => this.flushPendingEvents(), 80)
        }
        return
      }

      this.flushPendingEvents()
      this.events.push(event)

      if (event.name === 'message.created') {
        const messageItem = event.payload?.message
        if (this.chatType === 'group') {
          if (messageItem && messageItem.conversation_id === this.groupConversationId) {
            this.mergeMessage(messageItem)
          }
        } else if (messageItem) {
          this.mergeMessage(messageItem)
        }
        this.fetchActivity().catch(() => {})
        const currentId =
          this.chatType === 'group' ? this.groupConversationId : this.conversation?.conversation_id
        if (currentId) this.markSeen(currentId)
      }
      if (event.name === 'confirmation.requested' && event.payload?.confirmation) {
        this.mergeMessage(event.payload.confirmation)
      }
      if (event.name === 'human.confirmation.requested' && event.payload?.confirmation_id) {
        const item = event.payload
        if (!this.humanConfirmations.some((c) => c.confirmation_id === item.confirmation_id)) {
          this.humanConfirmations = [...this.humanConfirmations, item]
        }
      }
      if (event.name === 'human.confirmation.resolved' && event.payload?.confirmation_id) {
        this.humanConfirmations = this.humanConfirmations.filter(
          (c) => c.confirmation_id !== event.payload.confirmation_id,
        )
        this.pendingApprovals = this.pendingApprovals.filter(
          (c) => c.confirmation_id !== event.payload.confirmation_id,
        )
      }
      if (event.name === 'run.created') {
        const messageId = event.payload?.message_id
        const runId = event.payload?.run?.run_id
        if (messageId && runId) {
          this.messages = this.messages.map((item) =>
            item.message_id === messageId ? { ...item, run_id: runId } : item,
          )
        }
      }
      if (event.name === 'agent.reply.started') {
        const messageId = event.payload?.message_id
        this.messages = this.messages.map((item) =>
          item.message_id === messageId ? { ...item, status: 'running' } : item,
        )
      }
      if (event.name === 'run.cancelled' || (event.name === 'workflow.failed' && event.payload?.cancelled)) {
        const runId = event.payload?.run_id
        const messageId = event.payload?.message_id
        this.messages = this.messages.map((item) =>
          item.run_id === runId || item.message_id === messageId ? { ...item, status: 'cancelled' } : item,
        )
      }
      if (event.name === 'message.regenerated') {
        this.refreshMessages().catch(() => {})
      }
    },
  },
})
