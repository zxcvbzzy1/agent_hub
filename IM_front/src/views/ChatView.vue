<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import {
  BranchesOutlined,
  CheckOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DeleteOutlined,
  DeploymentUnitOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  RightOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  StopOutlined,
  TeamOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import {
  buildConversationTraces,
  buildGroupTimelineItems,
  compactLlmEvents,
  eventActor,
  eventColor,
  eventContent,
  eventTitle,
  eventTone,
  isPrimaryOutputEvent,
  runtimeEventNames,
  traceDuration,
} from '@/utils/runtimeEvents'
import { useAuthStore } from '@/stores/auth'
import { useIMStore } from '@/stores/im'

const im = useIMStore()
const auth = useAuthStore()
const listRef = ref(null)
const composerRef = ref(null)
const creatingRoom = ref(false)
const sending = ref(false)
const drawerOpen = ref(false)
const createOpen = ref(false)
const agentCreateOpen = ref(false)
const creatingAgent = ref(false)
const savingPlanner = ref(false)
const mentionOpen = ref(false)
const composer = ref('')
const mentions = ref([])
const drawerPlannerId = ref('default_planner')
const traceOpenOverrides = ref({})
const roomForm = reactive({
  type: 'group',
  title: '',
  member_agent_ids: [],
})
const agentForm = reactive({
  name: '',
  agent_type: 'executor',
  context_id: 'default_executor',
  description: '',
  role_prompt: '',
})
const dispatchOptions = reactive({
  auto_start: false,
  context_id: 'default_step',
  max_replan_rounds: 3,
})

const currentMembers = computed(() => {
  const ids = im.currentRoom?.member_agent_ids || []
  return ids.map(agentById).filter(Boolean)
})

const activeTitle = computed(() => {
  if (im.currentRoom) return im.currentRoom.title
  if (im.currentConversation) return im.currentConversation.title
  if (im.currentAgent) return im.currentAgent.name
  return '选择 Agent 或群聊'
})

const activeSubtitle = computed(() => {
  if (im.currentRoom?.type === 'group') return `${currentMembers.value.length} agents · PlanOrchestrator`
  if (im.currentAgent) return `${agentKind(im.currentAgent.agent_id)} · ${im.currentAgent.agent_type}`
  return '开始一次协作'
})

const roomAgentOptions = computed(() => {
  return im.executorAgents.map((agent) => ({
    label: `${agent.name} · ${agent.metadata?.agent_kind || 'native'}`,
    value: agent.agent_id,
}))
})

const contextOptions = computed(() => {
  const expectedKind = agentForm.agent_type === 'planner' ? 'planner' : 'executor'
  return im.contexts
    .filter((context) => !context.kind || context.kind === expectedKind)
    .map((context) => ({
      label: `${context.name || context.context_id} · ${context.kind || 'context'}`,
      value: context.context_id,
    }))
})

const mentionCandidates = computed(() => {
  if (im.currentRoom?.type !== 'group' || !mentionOpen.value) return []
  const lastAt = composer.value.lastIndexOf('@')
  const query = lastAt >= 0 ? composer.value.slice(lastAt + 1).trim().toLowerCase() : ''
  return currentMembers.value.filter((agent) => {
    return !query || agent.name.toLowerCase().includes(query) || agent.agent_id.toLowerCase().includes(query)
  })
})

const sideItems = computed(() => {
  if (im.currentRoom?.type === 'group') return im.tasks
  if (im.currentAgentId) return im.conversations
  return []
})

const displayEvents = computed(() => compactLlmEvents(im.events))

const runningGroupTask = computed(() => {
  if (im.currentRoom?.type !== 'group') return null
  return [...im.tasks]
    .filter((task) => task.run_id && ['running', 'pending', 'sent'].includes(task.status))
    .sort((a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0))[0] || null
})

const runningConversationMessage = computed(() => {
  if (im.currentRoom?.type === 'group') return null
  return [...im.messages]
    .filter((item) => item.sender_type === 'user' && item.status === 'running')
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))[0] || null
})

const canInterrupt = computed(() => {
  return im.currentRoom?.type === 'group' ? Boolean(runningGroupTask.value) : Boolean(runningConversationMessage.value)
})

const chatItems = computed(() => {
  if (im.currentRoom?.type === 'group') {
    return buildGroupTimelineItems({
      messages: im.messages,
      events: displayEvents.value.filter((event) => runtimeEventNames.has(event.name)),
    })
  }
  const traces = buildConversationTraces({
    messages: im.messages,
    events: displayEvents.value.filter((event) => runtimeEventNames.has(event.name)),
    conversationId: im.currentConversation?.conversation_id || '',
    agentId: im.currentConversation?.agent_id || im.currentAgentId,
  })
  const traceItems = traces.map((trace) => ({
    key: `trace-${trace.key}`,
    kind: 'trace',
    created_at: trace.insert_before_message_id
      ? (im.messages.find((message) => message.message_id === trace.insert_before_message_id)?.created_at || trace.created_at) - 0.0001
      : trace.created_at,
    trace,
  }))
  const messageItems = im.messages.map((message) => ({
    key: `message-${message.message_id}`,
    kind: 'message',
    created_at: message.created_at || 0,
    message,
  }))
  const eventItems = displayEvents.value
    .filter((event) => runtimeEventNames.has(event.name) && isPrimaryOutputEvent(event, 'dm'))
    .map((event) => ({
      key: `event-${event.event_id || `${event.name}-${event.created_at}`}`,
      kind: 'event',
      created_at: event.created_at || 0,
      event,
    }))
  return [...messageItems, ...traceItems, ...eventItems].sort((a, b) => a.created_at - b.created_at)
})

function agentById(agentId) {
  return im.agents.find((agent) => agent.agent_id === agentId)
}

function agentName(agentId) {
  return agentById(agentId)?.name || agentId || 'unknown'
}

function agentKind(agentId) {
  return agentById(agentId)?.metadata?.agent_kind || 'native'
}

function avatarText(value = '') {
  return (value || 'A').slice(0, 1).toUpperCase()
}

function itemAvatar(item) {
  if (item.type === 'group') return avatarText(item.title)
  return avatarText(item.name)
}

function messageTitle(item) {
  if (item.sender_type === 'user') {
    return item.sender_id === auth.user?.user_id ? '你' : item.sender_id
  }
  if (item.sender_type === 'system') return '系统'
  return agentName(item.sender_id)
}

function messageClass(item) {
  return {
    mine: item.sender_type === 'user' && item.sender_id === auth.user?.user_id,
    system: item.sender_type === 'system',
  }
}

function shortId(value = '') {
  return value ? value.slice(0, 8) : '-'
}

function formatTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleTimeString() : ''
}

function latestMessageText(item) {
  const source = item.last_message || item
  const part = source.content_parts?.find((entry) => entry.text || entry.diff || entry.title)
  return part?.text || part?.diff || part?.title || item.prompt || item.final || '暂无内容'
}

function isTraceOpen(trace) {
  if (Object.prototype.hasOwnProperty.call(traceOpenOverrides.value, trace.key)) {
    return traceOpenOverrides.value[trace.key]
  }
  return !trace.resolved
}

function toggleTrace(trace) {
  traceOpenOverrides.value = {
    ...traceOpenOverrides.value,
    [trace.key]: !isTraceOpen(trace),
  }
}

function traceActorName(trace) {
  if (trace.actor_id === 'workflow') return '系统流程'
  if (trace.actor_id === 'system') return '运行过程'
  if (trace.actor_id === 'planner') return agentName(im.currentRoom?.metadata?.planner_agent_id || 'default_planner')
  return agentName(trace.actor_id)
}

function traceTitle(trace) {
  return trace.title || eventTitle(trace.latest_event || {})
}

function traceStatusText(trace) {
  return trace.resolved ? `已完成 · ${traceDuration(trace)}` : `运行中 · ${traceDuration(trace)}`
}

function traceCanStop(trace) {
  if (trace.resolved) return false
  if (im.currentRoom?.type === 'group') return Boolean(trace.scope && trace.scope !== 'scope')
  return Boolean(runningConversationMessage.value)
}

function confirmInterruptActive() {
  if (!canInterrupt.value) return
  const isGroup = im.currentRoom?.type === 'group'
  Modal.confirm({
    title: isGroup ? '中断群聊编排？' : '中断单聊回复？',
    content: isGroup
      ? '将取消当前正在运行的 PlanOrchestrator run，并把对应用户消息标记为 cancelled。'
      : '将取消当前 Agent 回复任务，并把对应用户消息标记为 cancelled。',
    okText: '中断运行',
    okType: 'danger',
    cancelText: '继续等待',
    async onOk() {
      if (isGroup) {
        await im.cancelActiveRun(runningGroupTask.value?.run_id)
      } else {
        await im.cancelActiveReply(runningConversationMessage.value?.message_id)
      }
      message.warning('已发送中断请求')
    },
  })
}

function confirmInterruptTrace(trace) {
  if (!traceCanStop(trace)) return
  const isGroup = im.currentRoom?.type === 'group'
  Modal.confirm({
    title: isGroup ? '中断该运行轨迹对应的 run？' : '中断该回复？',
    content: '中断后后续输出会停止写入，当前消息会标记为 cancelled。',
    okText: '中断',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      if (isGroup) {
        await im.cancelActiveRun(trace.scope)
      } else {
        await im.cancelActiveReply(runningConversationMessage.value?.message_id)
      }
      message.warning('已发送中断请求')
    },
  })
}

function sideItemTitle(item) {
  if (im.currentRoom?.type === 'group') return item.status || item.mode || '编排任务'
  return item.title || `${agentName(item.agent_id)} 对话`
}

function sideItemTime(item) {
  return item.updated_at || item.last_message?.created_at || item.created_at
}

async function openSideItem(item) {
  if (im.currentRoom?.type === 'group') return
  if (item.conversation_id) await im.selectConversation(item.conversation_id)
}

async function newConversation() {
  if (!im.currentAgentId) return
  await im.createConversation(im.currentAgentId)
  await scrollToBottom()
}

async function createRoom() {
  if (!roomForm.member_agent_ids.length) {
    message.warning('请选择 agent')
    return
  }
  creatingRoom.value = true
  try {
    await im.createRoom({
      type: 'group',
      title: roomForm.title || 'Agent 群聊',
      member_agent_ids: [...roomForm.member_agent_ids],
      metadata: { source: 'IM_front' },
    })
    createOpen.value = false
    roomForm.title = ''
    roomForm.type = 'group'
    roomForm.member_agent_ids = []
    message.success('房间已创建')
  } finally {
    creatingRoom.value = false
  }
}

async function createAgent() {
  if (!agentForm.name.trim()) {
    message.warning('请输入 Agent 名称')
    return
  }
  creatingAgent.value = true
  try {
    await im.createAgent({
      name: agentForm.name.trim(),
      agent_type: agentForm.agent_type,
      context_id: agentForm.context_id || (agentForm.agent_type === 'planner' ? 'default_planner' : 'default_executor'),
      role_prompt: agentForm.role_prompt,
      metadata: {
        description: agentForm.description,
        capabilities: agentForm.description ? [agentForm.description] : [],
      },
    })
    agentCreateOpen.value = false
    agentForm.name = ''
    agentForm.agent_type = 'executor'
    agentForm.context_id = 'default_executor'
    agentForm.description = ''
    agentForm.role_prompt = ''
    message.success('Agent 已创建')
  } finally {
    creatingAgent.value = false
  }
}

function confirmDeleteAgent(agent) {
  Modal.confirm({
    title: `删除 Agent「${agent.name}」？`,
    content: '将同步删除该 Agent 的单聊对话、相关消息、事件，并从 Agent 群中移除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await im.deleteAgent(agent.agent_id)
      message.success('Agent 已删除')
    },
  })
}

function confirmDeleteConversation(item) {
  Modal.confirm({
    title: `删除对话「${item.title || '未命名对话'}」？`,
    content: '该对话的消息历史和运行事件会被硬删除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await im.deleteConversation(item.conversation_id)
      message.success('对话已删除')
    },
  })
}

function confirmDeleteRoom(room) {
  Modal.confirm({
    title: `解散 Agent 群「${room.title}」？`,
    content: '群消息、IM 事件、关联 run 和 runtime events 会同步删除。',
    okText: '解散',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await im.deleteRoom(room.room_id)
      message.success('Agent 群已解散')
    },
  })
}

async function saveGroupPlanner() {
  if (!im.currentRoom?.room_id) return
  savingPlanner.value = true
  try {
    await im.updateRoom(im.currentRoom.room_id, {
      metadata: {
        ...(im.currentRoom.metadata || {}),
        planner_agent_id: drawerPlannerId.value || 'default_planner',
      },
    })
    message.success('Planner 已更新')
  } finally {
    savingPlanner.value = false
  }
}

function handleInput(event) {
  const value = event.target.value
  composer.value = value
  const lastAt = value.lastIndexOf('@')
  mentionOpen.value = im.currentRoom?.type === 'group' && lastAt >= 0 && !value.slice(lastAt + 1).includes(' ')
}

function insertMention(agent) {
  const lastAt = composer.value.lastIndexOf('@')
  const before = lastAt >= 0 ? composer.value.slice(0, lastAt) : composer.value
  composer.value = `${before}@${agent.name} `
  if (!mentions.value.includes(agent.agent_id)) mentions.value.push(agent.agent_id)
  mentionOpen.value = false
  nextTick(() => composerRef.value?.focus?.())
}

async function send() {
  if (!im.currentRoom && !im.currentAgentId) {
    message.warning('请选择 agent 或群聊')
    return
  }
  if (!composer.value.trim()) return
  sending.value = true
  try {
    await im.sendMessage(
      {
        sender_type: 'user',
        content_parts: [{ type: 'text', text: composer.value.trim() }],
        mentions: [...mentions.value],
        metadata: { client: 'IM_front' },
      },
      {
        auto_start: im.currentRoom?.type === 'group' ? dispatchOptions.auto_start : true,
        planner_agent_id: im.currentRoom?.metadata?.planner_agent_id || drawerPlannerId.value || 'default_planner',
        context_id: dispatchOptions.context_id,
        max_replan_rounds: dispatchOptions.max_replan_rounds,
      },
    )
    composer.value = ''
    mentions.value = []
    mentionOpen.value = false
    await scrollToBottom()
  } finally {
    sending.value = false
  }
}

async function approveConfirmation(part) {
  const targetMessageId = part.metadata?.message_id
  if (!targetMessageId) return
  await im.recordAction(targetMessageId, {
    action_type: 'approve',
    payload: part.metadata,
  })
  await im.dispatch(targetMessageId, {
    approved: true,
    auto_start: true,
    planner_agent_id: im.currentRoom?.metadata?.planner_agent_id || drawerPlannerId.value || 'default_planner',
    context_id: dispatchOptions.context_id,
    max_replan_rounds: dispatchOptions.max_replan_rounds,
  })
  message.success('已批准并启动外部 Agent')
}

function copyText(text) {
  navigator.clipboard?.writeText(text)
  message.success('已复制')
}

async function scrollToBottom() {
  await nextTick()
  const el = listRef.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => chatItems.value.length,
  () => scrollToBottom(),
)

watch(
  () => agentForm.agent_type,
  (value) => {
    agentForm.context_id = value === 'planner' ? 'default_planner' : 'default_executor'
  },
)

watch(
  () => im.currentRoom?.metadata?.planner_agent_id,
  (value) => {
    drawerPlannerId.value = value || 'default_planner'
  },
  { immediate: true },
)

onMounted(async () => {
  await im.bootstrap()
  const defaultPlanner = im.plannerAgents.find((agent) => agent.agent_id === 'default_planner') || im.plannerAgents[0]
  if (defaultPlanner && !drawerPlannerId.value) drawerPlannerId.value = defaultPlanner.agent_id
  await scrollToBottom()
})
</script>

<template>
  <main class="im-workspace">
    <aside class="im-sidebar">
      <div class="sidebar-head">
        <div>
          <h2>会话</h2>
          <span>{{ im.executorAgents.length }} agents · {{ im.groupRooms.length }} groups</span>
        </div>
        <div class="sidebar-create-actions">
          <a-tooltip title="创建 Agent">
            <a-button type="primary" shape="circle" @click="agentCreateOpen = true">
              <template #icon><UserAddOutlined /></template>
            </a-button>
          </a-tooltip>
          <a-tooltip title="创建 Agent 群聊">
            <a-button shape="circle" @click="createOpen = true">
              <template #icon><PlusOutlined /></template>
            </a-button>
          </a-tooltip>
        </div>
      </div>

      <section class="nav-section">
        <div class="section-title">Agents</div>
        <button
          v-for="agent in im.executorAgents"
          :key="agent.agent_id"
          class="nav-card"
          :class="{ active: im.currentAgentId === agent.agent_id && im.currentRoom?.type !== 'group' }"
          @click="im.selectAgent(agent.agent_id)"
        >
          <a-avatar :src="agent.metadata?.avatar_url">{{ itemAvatar(agent) }}</a-avatar>
          <span class="presence"></span>
          <div>
            <strong>{{ agent.name }}</strong>
            <small>{{ agentKind(agent.agent_id) }}</small>
          </div>
          <a-button
            v-if="!['default_executor', 'default_planner'].includes(agent.agent_id)"
            class="nav-delete"
            type="text"
            danger
            size="small"
            @click.stop="confirmDeleteAgent(agent)"
          >
            <template #icon><DeleteOutlined /></template>
          </a-button>
        </button>
      </section>

      <section class="nav-section">
        <div class="section-title">Agent 群</div>
        <button
          v-for="room in im.groupRooms"
          :key="room.room_id"
          class="nav-card"
          :class="{ active: im.currentRoom?.room_id === room.room_id }"
          @click="im.selectGroupRoom(room.room_id)"
        >
          <a-avatar :src="room.avatar_url"><TeamOutlined /></a-avatar>
          <div>
            <strong>{{ room.title }}</strong>
            <small>{{ room.member_agent_ids.length }} members</small>
          </div>
          <a-button class="nav-delete" type="text" danger size="small" @click.stop="confirmDeleteRoom(room)">
            <template #icon><DeleteOutlined /></template>
          </a-button>
        </button>
      </section>

      <section class="side-feed">
        <div class="side-feed-head">
          <div class="section-title">{{ im.currentRoom?.type === 'group' ? '编排任务' : '对话列表' }}</div>
          <a-button
            v-if="im.currentAgentId && im.currentRoom?.type !== 'group'"
            type="text"
            size="small"
            @click="newConversation"
          >
            <template #icon><PlusOutlined /></template>
            新对话
          </a-button>
        </div>
        <a-empty v-if="!sideItems.length" description="暂无记录" />
        <button
          v-for="item in sideItems"
          :key="item.conversation_id || item.message_id || item.task_id"
          class="feed-item"
          :class="{ active: item.conversation_id && item.conversation_id === im.currentConversation?.conversation_id }"
          @click="openSideItem(item)"
        >
          <strong>{{ sideItemTitle(item) }}</strong>
          <span>{{ latestMessageText(item) }}</span>
          <small>{{ formatTime(sideItemTime(item)) }}</small>
          <a-button
            v-if="item.conversation_id"
            class="feed-delete"
            type="text"
            danger
            size="small"
            @click.stop="confirmDeleteConversation(item)"
          >
            <template #icon><DeleteOutlined /></template>
          </a-button>
        </button>
      </section>
    </aside>

    <section class="chat-main">
      <header class="chat-hero" @click="drawerOpen = true">
        <div class="hero-title">
          <a-avatar :size="44">
            <TeamOutlined v-if="im.currentRoom?.type === 'group'" />
            <RobotOutlined v-else />
          </a-avatar>
          <div>
            <h1>{{ activeTitle }}</h1>
            <p>{{ activeSubtitle }}</p>
          </div>
        </div>
        <div class="hero-actions">
          <a-button
            v-if="canInterrupt"
            danger
            class="hero-stop"
            @click.stop="confirmInterruptActive"
          >
            <template #icon><StopOutlined /></template>
            中断运行
          </a-button>
          <a-space v-if="im.currentRoom?.type === 'group'" @click.stop>
            <a-switch v-model:checked="dispatchOptions.auto_start" />
            <span class="muted">自动启动</span>
          </a-space>
          <span class="hero-info-chip">
            <InfoCircleOutlined />
            查看信息
            <RightOutlined />
          </span>
        </div>
      </header>

      <div ref="listRef" class="message-list">
        <a-empty v-if="!chatItems.length" description="暂无消息" />
        <template v-for="entry in chatItems" :key="entry.key">
          <article
            v-if="entry.kind === 'message'"
            class="message-row"
            :class="messageClass(entry.message)"
          >
            <a-avatar class="message-avatar">{{ avatarText(messageTitle(entry.message)) }}</a-avatar>
            <div class="message-bubble">
              <div class="message-meta">
                <strong>{{ messageTitle(entry.message) }}</strong>
                <span>{{ formatTime(entry.message.created_at) }}</span>
                <a-tag v-if="entry.message.status !== 'sent'" size="small">{{ entry.message.status }}</a-tag>
                <a-tag v-if="entry.message.run_id && im.currentRoom?.type === 'group'" size="small" color="blue">
                  run {{ shortId(entry.message.run_id) }}
                </a-tag>
              </div>

              <div v-for="(part, index) in entry.message.content_parts" :key="`${entry.message.message_id}-${index}`" class="part">
                <p v-if="part.type === 'text'" class="text-part">{{ part.text }}</p>
                <pre v-else-if="part.type === 'code'" class="code-part"><code>{{ part.text }}</code></pre>
                <img v-else-if="part.type === 'image'" class="image-part" :src="part.url" :alt="part.name || 'image'" />
                <a-button v-else-if="part.type === 'file'" :href="part.url" target="_blank">
                  <template #icon><FileTextOutlined /></template>
                  {{ part.name || '文件' }}
                </a-button>
                <a :href="part.url" target="_blank" v-else-if="part.type === 'web_preview'" class="web-card">
                  <strong>{{ part.title || part.url }}</strong>
                  <span>{{ part.description }}</span>
                </a>
                <div v-else-if="part.type === 'diff'" class="diff-card">
                  <div class="card-title">
                    <BranchesOutlined />
                    <span>{{ part.title || 'Diff' }}</span>
                    <a-button size="small" type="text" @click="copyText(part.diff)">
                      <template #icon><CopyOutlined /></template>
                    </a-button>
                  </div>
                  <pre><code>{{ part.diff }}</code></pre>
                </div>
                <div v-else-if="part.type === 'deploy'" class="deploy-card">
                  <div class="card-title">
                    <DeploymentUnitOutlined />
                    <span>{{ part.title || '操作卡片' }}</span>
                  </div>
                  <p>{{ part.description }}</p>
                  <a-space v-if="part.metadata?.message_id">
                    <a-button type="primary" size="small" @click="approveConfirmation(part)">
                      <template #icon><CheckOutlined /></template>
                      批准
                    </a-button>
                    <a-tag color="orange">
                      <SafetyCertificateOutlined />
                      人工确认
                    </a-tag>
                  </a-space>
                </div>
                <a-tag v-else color="default">{{ part.type }}</a-tag>
              </div>
            </div>
          </article>

          <article v-else-if="entry.kind === 'trace'" class="trace-card" :class="{ open: isTraceOpen(entry.trace) }">
            <button class="trace-summary" @click="toggleTrace(entry.trace)">
              <span class="trace-rail"></span>
              <a-avatar class="trace-avatar">{{ avatarText(traceActorName(entry.trace)) }}</a-avatar>
              <div class="trace-main">
                <strong>{{ traceActorName(entry.trace) }}</strong>
                <span>{{ traceTitle(entry.trace) }}</span>
              </div>
              <div class="trace-stats">
                <a-tag :color="eventColor(entry.trace.latest_event?.name)" size="small">
                  {{ entry.trace.event_count || entry.trace.events.length }} events
                </a-tag>
                <small>{{ traceStatusText(entry.trace) }}</small>
              </div>
              <a-button
                v-if="traceCanStop(entry.trace)"
                class="trace-stop"
                danger
                type="text"
                size="small"
                @click.stop="confirmInterruptTrace(entry.trace)"
              >
                <template #icon><StopOutlined /></template>
              </a-button>
              <RightOutlined class="trace-chevron" />
            </button>

            <div v-if="isTraceOpen(entry.trace)" class="trace-expanded">
              <div v-if="entry.trace.step?.result_observation" class="trace-observation">
                {{ entry.trace.step.result_observation }}
              </div>
              <div class="trace-timeline">
                <div
                  v-for="event in entry.trace.events"
                  :key="event.event_id || `${event.name}-${event.created_at}`"
                  class="trace-node"
                  :class="eventTone(event.name)"
                >
                  <span class="trace-dot"></span>
                  <div class="trace-node-body">
                    <div class="trace-node-head">
                      <strong>{{ eventTitle(event) }}</strong>
                      <a-tag :color="eventColor(event.name)" size="small">{{ event.name }}</a-tag>
                      <span>{{ formatTime(event.created_at) }}</span>
                    </div>
                    <pre>{{ eventContent(event, agentName) }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </article>

          <article v-else class="message-row event-row">
            <a-avatar class="message-avatar">{{ avatarText(eventActor(entry.event, agentName)) }}</a-avatar>
            <div class="message-bubble event-bubble" :class="eventTone(entry.event.name)">
              <div class="message-meta">
                <strong>{{ eventActor(entry.event, agentName) }}</strong>
                <a-tag :color="eventColor(entry.event.name)" size="small">{{ eventTitle(entry.event) }}</a-tag>
                <span>{{ formatTime(entry.event.created_at) }}</span>
              </div>
              <pre class="event-content">{{ eventContent(entry.event, agentName) }}</pre>
            </div>
          </article>
        </template>
      </div>

      <footer class="composer">
        <div class="mention-wrap">
          <div v-if="mentionCandidates.length" class="mention-popover">
            <button v-for="agent in mentionCandidates" :key="agent.agent_id" @click="insertMention(agent)">
              <a-avatar :size="24">{{ avatarText(agent.name) }}</a-avatar>
              <span>{{ agent.name }}</span>
              <small>{{ agentKind(agent.agent_id) }}</small>
            </button>
          </div>
          <a-textarea
            ref="composerRef"
            :value="composer"
            :auto-size="{ minRows: 2, maxRows: 6 }"
            :placeholder="im.currentRoom?.type === 'group' ? '输入消息。输入 @ 可选择群内 agent' : '输入消息，当前会话历史会注入给这个 agent'"
            @input="handleInput"
            @pressEnter.ctrl.prevent="send"
          />
        </div>
        <div class="composer-actions">
          <a-space v-if="im.currentRoom?.type === 'group'">
            <a-input-number v-model:value="dispatchOptions.max_replan_rounds" :min="0" :max="10" />
          </a-space>
          <a-button type="primary" :loading="sending" @click="send">
            <template #icon><SendOutlined /></template>
            发送
          </a-button>
        </div>
      </footer>

    </section>

    <a-modal v-model:open="createOpen" title="创建 Agent 群聊" :footer="null">
      <a-form layout="vertical">
        <a-form-item label="名称">
          <a-input v-model:value="roomForm.title" placeholder="留空则自动命名为 Agent 群聊" />
        </a-form-item>
        <a-form-item label="群成员 Agent">
          <a-select
            v-model:value="roomForm.member_agent_ids"
            mode="multiple"
            :options="roomAgentOptions"
            placeholder="选择 agent"
            show-search
          />
        </a-form-item>
        <a-button type="primary" html-type="submit" block :loading="creatingRoom" @click="createRoom">创建</a-button>
      </a-form>
    </a-modal>

    <a-modal v-model:open="agentCreateOpen" title="创建 Agent" :footer="null">
      <a-form layout="vertical">
        <a-form-item label="名称">
          <a-input v-model:value="agentForm.name" placeholder="例如：前端组件工程师" />
        </a-form-item>
        <a-form-item label="类型">
          <a-segmented
            v-model:value="agentForm.agent_type"
            :options="[
              { label: 'Executor', value: 'executor' },
              { label: 'Planner', value: 'planner' },
            ]"
          />
        </a-form-item>
        <a-form-item label="Context">
          <a-select
            v-model:value="agentForm.context_id"
            :options="contextOptions"
            :placeholder="agentForm.agent_type === 'planner' ? 'default_planner' : 'default_executor'"
            show-search
          />
        </a-form-item>
        <a-form-item label="能力描述">
          <a-input v-model:value="agentForm.description" placeholder="擅长方向、可承担任务或工具范围" />
        </a-form-item>
        <a-form-item label="Role Prompt">
          <a-textarea v-model:value="agentForm.role_prompt" :auto-size="{ minRows: 4, maxRows: 8 }" />
        </a-form-item>
        <a-button type="primary" html-type="submit" block :loading="creatingAgent" @click="createAgent">
          创建 Agent
        </a-button>
      </a-form>
    </a-modal>

    <a-drawer v-model:open="drawerOpen" title="上下文信息" width="420">
      <section class="drawer-section">
        <h3>{{ im.currentRoom?.type === 'group' ? '群内 Agent' : 'Agent 信息' }}</h3>
        <div v-if="im.currentRoom?.type === 'group'" class="orchestrator-card">
          <strong>{{ im.currentRoom?.metadata?.orchestrator || 'PlanOrchestrator' }}</strong>
          <span>Planner · {{ agentName(im.currentRoom?.metadata?.planner_agent_id || 'default_planner') }}</span>
          <small>{{ currentMembers.length }} executor agents</small>
        </div>
        <div v-if="im.currentRoom?.type === 'group'" class="planner-config">
          <label>Plan Agent</label>
          <a-space-compact block>
            <a-select v-model:value="drawerPlannerId" class="drawer-planner-select">
              <a-select-option v-for="agent in im.plannerAgents" :key="agent.agent_id" :value="agent.agent_id">
                {{ agent.name }}
              </a-select-option>
            </a-select>
            <a-button type="primary" :loading="savingPlanner" @click="saveGroupPlanner">更换</a-button>
          </a-space-compact>
          <small>群聊 dispatch 会读取这里配置的 planner。</small>
        </div>
        <a-list :data-source="im.currentRoom?.type === 'group' ? currentMembers : [im.currentAgent].filter(Boolean)">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar><a-avatar :src="item.metadata?.avatar_url">{{ avatarText(item.name) }}</a-avatar></template>
                <template #title>{{ item.name }}</template>
                <template #description>
                  {{ item.agent_id }} · {{ item.metadata?.agent_kind || 'native' }}
                </template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </section>

      <section v-if="im.currentRoom?.type !== 'group'" class="drawer-section">
        <h3>该 Agent 的对话</h3>
        <a-empty v-if="!im.conversations.length" description="暂无对话" />
        <a-list :data-source="im.conversations">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar><RobotOutlined /></template>
                <template #title>{{ item.title || '未命名对话' }}</template>
                <template #description>
                  {{ latestMessageText(item) }} · {{ item.message_count || 0 }} 条消息
                </template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </section>

      <section class="drawer-section">
        <h3>上传文件</h3>
        <a-empty v-if="!im.artifacts.length" description="暂无文件" />
        <a-list :data-source="im.artifacts">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar><FileTextOutlined /></template>
                <template #title>{{ item.filename }}</template>
                <template #description>{{ item.content_type || 'file' }} · {{ item.size }} bytes</template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </section>

      <section v-if="im.currentRoom?.type === 'group'" class="drawer-section">
        <h3>最近任务</h3>
        <a-list :data-source="im.tasks.slice(0, 6)">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar><CloudUploadOutlined /></template>
                <template #title>{{ item.status || item.mode }}</template>
                <template #description>{{ item.prompt }}</template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </section>
    </a-drawer>
  </main>
</template>
