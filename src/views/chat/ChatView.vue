<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  AppstoreOutlined,
  CommentOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons-vue'
import EventTimeline from '@/components/workflow/EventTimeline.vue'
import ExecutorEventPanel from '@/components/workflow/ExecutorEventPanel.vue'
import JsonBlock from '@/components/workflow/JsonBlock.vue'
import { runsApi } from '@/api/runs'
import { useAutoScroll } from '@/composables/useAutoScroll'
import { useAgentsStore } from '@/stores/agents'
import { useConversationsStore } from '@/stores/conversations'
import { useContextsStore } from '@/stores/contexts'
import { useRunsStore } from '@/stores/runs'

const conversations = useConversationsStore()
const agents = useAgentsStore()
const contexts = useContextsStore()
const runs = useRunsStore()
const activeRunId = ref('')
const selectedExecutor = ref('')
const input = ref('请帮我分析 agent_flow 后端 API 能力')
const listRef = ref(null)
const executorOutputRef = ref(null)
const executorEventsRef = ref(null)
const conversationRailCollapsed = ref(true)
const conversationDrawerOpen = ref(false)
const configModalOpen = ref(false)
const eventDrawerOpen = ref(false)
const selectedEvent = ref(null)
const resolving = ref({})
const cancelingRun = ref(false)
const executorOutputPlacement = ref('side')
const executorPanelTab = ref('outputs')
const chatMode = ref('react')
const terminalRunStatuses = new Set(['finished', 'failed', 'cancelled'])

const plannerMessageNames = new Set([
  'planner.plan.generated',
  'planner.replan.reasoning',
  'planner.final',
])

const executorOutputNames = new Set([
  'agent.think',
  'agent.tool.reasoning',
  'agent.final',
])

const reactForm = reactive({
  executor_agent_id: 'default_executor',
})

const planForm = reactive({
  planner_agent_id: 'default_planner',
  executor_agent_ids: ['default_executor'],
  context_id: 'default_step',
  max_replan_rounds: 3,
})

const plannerAgents = computed(() => agents.items.filter((item) => item.agent_type === 'planner'))
const executorAgents = computed(() => agents.items.filter((item) => item.agent_type === 'executor'))
const stepContexts = computed(() => contexts.items.filter((item) => item.kind === 'step'))
const executorOptions = computed(() => {
  const activeExecutors = runs.current?.executor_agent_ids
  if (activeExecutors?.length) return activeExecutors
  if (chatMode.value === 'react') return [reactForm.executor_agent_id].filter(Boolean)
  return planForm.executor_agent_ids
})
const modeConfigSummary = computed(() => {
  if (chatMode.value === 'react') {
    return `React · ${agentLabel(reactForm.executor_agent_id)}`
  }
  return [
    `Plan · ${agentLabel(planForm.planner_agent_id)}`,
    `${planForm.executor_agent_ids.length} executors`,
    contextLabel(planForm.context_id),
  ].join(' · ')
})

const currentEvents = computed(() => {
  return activeRunId.value ? runs.eventsByRun[activeRunId.value] || [] : []
})

const sortedEvents = computed(() => {
  return [...currentEvents.value].sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
})

const displayEvents = computed(() => compactLlmEvents(sortedEvents.value))
const ordinaryEvents = computed(() => {
  return displayEvents.value.filter((event) => !isPlannerMessageEvent(event) && !isExecutorOutputEvent(event))
})
const executorEvents = computed(() => ordinaryEvents.value.filter(isExecutorEvent))
const orchestratorEvents = computed(() => ordinaryEvents.value.filter((event) => !isExecutorEvent(event)))
const plannerMessageEvents = computed(() => displayEvents.value.filter(isPlannerMessageEvent))
const allExecutorOutputEvents = computed(() => displayEvents.value.filter(isExecutorOutputEvent))
const visibleExecutorOutputEvents = computed(() => {
  if (executorOutputPlacement.value === 'main') return []
  return allExecutorOutputEvents.value.filter(matchesSelectedExecutor)
})
const mainChatItems = computed(() => {
  const conversationItems = conversations.messages.map((item) => ({
    key: `message-${item.message_id}`,
    kind: 'conversation',
    created_at: item.created_at || 0,
    message: item,
  }))
  const outputEvents = [
    ...plannerMessageEvents.value,
    ...(executorOutputPlacement.value === 'main' ? allExecutorOutputEvents.value : []),
  ]
  const outputItems = outputEvents.map((event) => ({
    key: `agent-output-${event.event_id || `${event.name}-${event.created_at}`}`,
    kind: 'agent-output',
    created_at: event.created_at || 0,
    output: agentOutputMessageFromEvent(event),
    event,
  }))
  const eventItems = orchestratorEvents.value.map((event) => ({
    key: `event-${event.event_id || `${event.name}-${event.created_at}`}`,
    kind: 'event',
    created_at: event.created_at || 0,
    event,
  }))
  return [...conversationItems, ...outputItems, ...eventItems].sort((a, b) => a.created_at - b.created_at)
})
const latestExecutorPayload = computed(() => {
  const latestOutput = visibleExecutorOutputEvents.value.at(-1)
  const latestEvent = executorEvents.value.at(-1)
  return latestOutput?.payload || latestEvent?.payload || { status: 'waiting' }
})
const activeRunRecord = computed(() => {
  return runs.current?.run_id === activeRunId.value ? runs.current : null
})
const canCancelActiveRun = computed(() => {
  if (!activeRunId.value || cancelingRun.value) return false
  const status = activeRunRecord.value?.status
  return !terminalRunStatuses.has(status)
})
const resolvedConfirmationIds = computed(() => {
  return new Set(
    currentEvents.value
      .filter((event) => event.name === 'human.confirmation.resolved' && event.payload?.confirmation_id)
      .map((event) => event.payload.confirmation_id),
  )
})

const runStats = computed(() => {
  const failed = currentEvents.value.filter((event) => event.name?.includes('failed')).length
  const pending = currentEvents.value.filter((event) => {
    return event.name === 'human.confirmation.requested' && event.payload?.status === 'pending'
  }).length
  return {
    events: currentEvents.value.length,
    failed,
    pending,
  }
})

const latestMessageRunId = computed(() => {
  const messageWithRun = [...conversations.messages].reverse().find((item) => item.run_id)
  return messageWithRun?.run_id || ''
})

const { scrollToBottom: scrollMainToBottom } = useAutoScroll(
  listRef,
  () => mainChatItems.value.length,
)
useAutoScroll(
  executorOutputRef,
  () => [visibleExecutorOutputEvents.value.length, executorPanelTab.value],
)
useAutoScroll(
  executorEventsRef,
  () => [executorEvents.value.length, executorPanelTab.value],
)

const selectedEventMeta = computed(() => {
  const payload = selectedEvent.value?.payload || {}
  const step = payload.step || {}
  return [
    { label: 'Run ID', value: selectedEvent.value?.run_id || payload.run_id || activeRunId.value || '-' },
    { label: 'Agent', value: payload.agent_id || '-' },
    { label: 'Executor', value: payload.executor_id || step.executor_id || '-' },
    { label: 'Step', value: payload.step_id || step.step_id || '-' },
    { label: 'Tool', value: payload.tool_name || payload.name || '-' },
    { label: 'Call Role', value: payload.call_role || '-' },
  ]
})

function isExecutorEvent(event) {
  const name = event?.name || ''
  const payload = event?.payload || {}
  const step = payload.step || {}
  if (isPlannerMessageEvent(event) || isExecutorOutputEvent(event)) return false
  if (name.startsWith('planner.')) return false
  if (name.startsWith('llm.')) return payload.agent_type === 'executor'
  if (name.startsWith('agent.')) return payload.agent_type === 'executor'
  if (name.startsWith('workflow.') || name.startsWith('plan.') || name.startsWith('human.confirmation.')) {
    return false
  }
  if (name.startsWith('tool.') || name === 'agent.failed') return true
  return Boolean(payload.executor_id || step.executor_id || payload.tool_name)
}

function isPlannerMessageEvent(event) {
  return plannerMessageNames.has(event?.name)
}

function isExecutorOutputEvent(event) {
  if (!executorOutputNames.has(event?.name)) return false
  const payload = event?.payload || {}
  if (payload.agent_type === 'planner') return false
  if (payload.agent_type === 'executor') return true
  if (payload.executor_id || payload.step?.executor_id || payload.tool_name) return true
  if (selectedExecutor.value) return JSON.stringify(payload).includes(selectedExecutor.value)
  return true
}

function matchesSelectedExecutor(event) {
  if (!selectedExecutor.value) return true
  const payload = event?.payload || {}
  const step = payload.step || {}
  return (
    payload.agent_id === selectedExecutor.value ||
    payload.executor_id === selectedExecutor.value ||
    step.executor_id === selectedExecutor.value ||
    JSON.stringify(payload).includes(selectedExecutor.value)
  )
}

function eventColor(name = '') {
  if (name.includes('failed')) return 'red'
  if (name.includes('finished')) return 'green'
  if (name.startsWith('human.confirmation')) return 'orange'
  if (name.startsWith('llm.')) return 'cyan'
  if (name.startsWith('agent.')) return 'geekblue'
  if (name.startsWith('planner.')) return 'purple'
  if (name.startsWith('plan.')) return 'purple'
  if (name.startsWith('workflow.')) return 'blue'
  return 'default'
}

function eventTone(name = '') {
  if (name.includes('failed')) return 'danger'
  if (name.includes('finished')) return 'success'
  if (name.startsWith('human.confirmation')) return 'warning'
  if (name.startsWith('llm.')) return 'stream'
  if (name.startsWith('agent.')) return 'agent'
  if (name.startsWith('planner.')) return 'plan'
  if (name.startsWith('plan.')) return 'plan'
  return 'workflow'
}

function eventSummary(event) {
  const payload = event?.payload || {}
  const step = payload.step || {}
  if (event?.name === 'llm.streaming') return `${payload.agent_name || payload.agent_id} 正在输出`
  if (event?.name === 'llm.completed') return `${payload.agent_name || payload.agent_id} 输出完成`
  if (event?.name === 'agent.think') return payload.think || 'Agent 思考'
  if (event?.name === 'agent.tool.reasoning') return payload.reasoning || `调用工具 ${payload.tool_name}`
  if (event?.name === 'agent.final') return payload.final || payload.finish_reason || 'Agent 完成'
  if (event?.name === 'planner.plan.generated') return `生成 ${payload.steps?.length || 0} 个计划步骤`
  if (event?.name === 'planner.replan.reasoning') return payload.reason || payload.action || 'Plan Agent 重规划'
  if (event?.name === 'planner.final') return payload.final || 'Plan Agent 总结'
  if (step.title) return step.title
  if (payload.tool_name) return `工具 ${payload.tool_name}`
  if (payload.status_reason) return payload.status_reason
  if (payload.reason) return payload.reason
  if (payload.error) return payload.error
  if (payload.final) return payload.final
  return '查看事件负载'
}

function agentOutputMessageFromEvent(event) {
  const payload = event?.payload || {}
  const name = event?.name || ''
  if (name === 'planner.plan.generated') {
    return {
      role: 'Plan Agent',
      title: `生成计划 · ${payload.steps?.length || 0} steps`,
      content: convertPlanToString(payload),
      tone: 'planner',
      meta: payload.planner_id || payload.agent_id || 'planner',
    }
  }
  if (name === 'planner.replan.reasoning') {
    return {
      role: 'Plan Agent',
      title: '重规划',
      content: [payload.action, payload.reason].filter(Boolean).join('\n') || 'Plan Agent 发起重规划',
      tone: 'planner',
      meta: payload.planner_id || payload.agent_id || 'planner',
    }
  }
  if (name === 'planner.final') {
    return {
      role: 'Plan Agent',
      title: '最终总结',
      content: payload.final || payload.content || 'Plan Agent 已完成总结',
      tone: 'planner final',
      meta: payload.planner_id || payload.agent_id || 'planner',
    }
  }
  if (name === 'agent.think') {
    return {
      role: payload.agent_name || payload.agent_id || 'Executor Agent',
      title: '思考',
      content: payload.think || payload.content || 'Agent 正在思考',
      tone: 'executor think',
      meta: payload.agent_id || payload.executor_id || 'executor',
    }
  }
  if (name === 'agent.tool.reasoning') {
    return {
      role: payload.agent_name || payload.agent_id || 'Executor Agent',
      title: `工具决策${payload.tool_name ? ` · ${payload.tool_name}` : ''}`,
      content: payload.reasoning || payload.reason || `准备调用工具 ${payload.tool_name || ''}`.trim(),
      tone: 'executor reasoning',
      meta: payload.agent_id || payload.executor_id || payload.tool_name || 'executor',
    }
  }
  return {
    role: payload.agent_name || payload.agent_id || 'Executor Agent',
    title: '执行结果',
    content: payload.final || payload.finish_reason || payload.content || 'Agent 已完成',
    tone: 'executor final',
    meta: payload.agent_id || payload.executor_id || 'executor',
  }
}

function payloadPreview(event) {
  const payload = event?.payload || {}
  const preview = {
    agent: payload.agent_name || payload.agent_id,
    call_role: payload.call_role,
    content: event?.name === 'llm.streaming' ? payload.content : undefined,
    think: payload.think,
    reasoning: payload.reasoning,
    final: payload.final,
    agent_id: payload.agent_id,
    executor_id: payload.executor_id || payload.step?.executor_id,
    tool_name: payload.tool_name || payload.name,
    status: payload.status || payload.step?.status,
    respond: payload.respond,
    reason: payload.reason || payload.status_reason,
    arguments: payload.arguments,
  }
  return Object.fromEntries(Object.entries(preview).filter(([, value]) => value !== undefined && value !== ''))
}

function convertPlanToString(jsonData) {
  // 1. 安全检查，防止传入空数据或格式不正确的数据
  if (!jsonData || !jsonData.steps || !Array.isArray(jsonData.steps)) {
    return "错误：无效的计划数据格式";
  }

  const steps = jsonData.steps;
  
  // 2. 遍历并映射每一个步骤
  const lines = steps.map(step => {
    // 处理依赖项：如果是空数组则显示“无”，否则用逗号拼接
    const dependsOnStr = step.depends_on && step.depends_on.length > 0 
      ? step.depends_on.join(', ') 
      : '无';
    // 组装单个步骤的中文文本
    return `步骤 ID: ${step.step_id}
标题: ${step.title}
指令说明: ${step.instruction}
执行器名称: ${agentLabel(step.executor_id)}
依赖步骤: ${dependsOnStr}`;
  });
  // 3. 用双换行和分割线把所有步骤拼接在一起
  return lines.join('\n----------------------------------------\n');
}

function compactLlmEvents(events) {
  const compacted = []
  const streaming = new Map()

  for (const event of events) {
    if (event.name === 'llm.delta') {
      const payload = event.payload || {}
      const key = `${payload.agent_id || 'unknown'}:${payload.call_role || 'unknown'}`
      const current = streaming.get(key) || {
        ...event,
        event_id: `streaming-${key}`,
        name: 'llm.streaming',
        payload: {
          ...payload,
          content: '',
          token_chunks: 0,
          streaming: true,
        },
      }
      current.payload.content += payload.delta || ''
      current.payload.token_chunks = payload.sequence || current.payload.token_chunks + 1
      current.created_at = event.created_at
      streaming.set(key, current)
      continue
    }

    if (event.name === 'llm.completed') {
      const payload = event.payload || {}
      const key = `${payload.agent_id || 'unknown'}:${payload.call_role || 'unknown'}`
      streaming.delete(key)
      compacted.push(event)
      continue
    }

    if (event.name === 'llm.started') {
      continue
    }

    compacted.push(event)
  }

  compacted.push(...streaming.values())
  return compacted.sort((a, b) => (a.created_at || 0) - (b.created_at || 0))
}

function eventTime(event) {
  return event?.created_at ? new Date(event.created_at * 1000).toLocaleTimeString() : ''
}

function shortId(value = '') {
  return value ? value.slice(0, 8) : '-'
}

function currentInitial() {
  const title = conversations.current?.title || '会'
  return title.slice(0, 1).toUpperCase()
}

function agentLabel(agentId = '') {
  const agent = agents.items.find((item) => item.agent_id === agentId)
  return agent?.name || agentId || '-'
}

function contextLabel(contextId = '') {
  const context = contexts.items.find((item) => item.context_id === contextId)
  return context?.name || contextId || '-'
}

async function ensureConversation() {
  if (conversations.current) return conversations.current
  return conversations.createConversation({ title: 'Agent 对话', metadata: {} })
}

async function sendMessage() {
  if (!input.value.trim()) return
  if (!validateRunConfig()) return
  const conversation = await ensureConversation()
  const messageItem = await conversations.addMessage(conversation.conversation_id, {
    role: 'user',
    content: input.value,
    metadata: {},
  })
  const run = await conversations.createRun(conversation.conversation_id, buildRunPayload(messageItem.message_id))
  activateRun(run.run_id, run)
  input.value = ''
  scrollMainToBottom()
  message.success('已发送并启动 Run')
}

function validateRunConfig() {
  if (chatMode.value === 'react' && !reactForm.executor_agent_id) {
    message.warning('请选择 executor agent')
    return false
  }
  if (chatMode.value === 'plan' && (!planForm.planner_agent_id || !planForm.executor_agent_ids.length || !planForm.context_id)) {
    message.warning('请完整选择 planner、executors 和 step context')
    return false
  }
  return true
}

function buildRunPayload(messageId) {
  if (chatMode.value === 'react') {
    return {
      mode: 'react',
      message_id: messageId,
      executor_agent_id: reactForm.executor_agent_id,
      auto_start: true,
    }
  }
  return {
    mode: 'plan',
    message_id: messageId,
    planner_agent_id: planForm.planner_agent_id,
    executor_agent_ids: [...planForm.executor_agent_ids],
    context_id: planForm.context_id,
    max_replan_rounds: planForm.max_replan_rounds,
    auto_start: true,
  }
}

async function activateRun(runId, runRecord = null) {
  if (!runId) return
  activeRunId.value = runId
  if (runRecord) {
    runs.current = runRecord
  } else {
    runs.fetchRun(runId).catch(() => {})
  }
  selectedExecutor.value = runRecord?.executor_agent_ids?.[0] || runs.current?.executor_agent_ids?.[0] || selectedExecutor.value
  runs.connect(runId)
}

async function cancelActiveRun() {
  if (!canCancelActiveRun.value) return
  cancelingRun.value = true
  try {
    await runs.cancelRun(activeRunId.value)
    message.success('Run 已中断')
  } finally {
    cancelingRun.value = false
  }
}

async function selectConversation(id) {
  await conversations.selectConversation(id)
  const runId = latestMessageRunId.value
  if (runId) activateRun(runId)
  conversationDrawerOpen.value = false
}

function confirmDeleteConversation(conversation = conversations.current) {
  if (!conversation?.conversation_id) return
  Modal.confirm({
    title: '删除会话',
    content: `确认删除「${conversation.title}」及其消息、Run 和事件吗？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      const deletingCurrent = conversation.conversation_id === conversations.current?.conversation_id
      await conversations.deleteConversation(conversation.conversation_id)
      message.success('会话已删除')
      if (!deletingCurrent) return

      activeRunId.value = ''
      selectedExecutor.value = ''
      runs.current = null
      const next = conversations.items[0]
      if (next) {
        await selectConversation(next.conversation_id)
      }
    },
  })
}

function openEmbeddedRoute() {
  if (activeRunId.value) {
    window.open(`/executor-frame/${activeRunId.value}/${selectedExecutor.value || ''}`, '_blank')
  }
}

function openEvent(event) {
  selectedEvent.value = event
  eventDrawerOpen.value = true
}

function isConfirmationRequest(event) {
  return (
    event?.name === 'human.confirmation.requested' &&
    event.payload?.status === 'pending' &&
    !isConfirmationResolved(event)
  )
}

function isConfirmationResolved(event) {
  const confirmationId = event?.payload?.confirmation_id
  return Boolean(confirmationId && resolvedConfirmationIds.value.has(confirmationId))
}

async function resolveSelectedConfirmation(approved) {
  const payload = selectedEvent.value?.payload || {}
  if (isConfirmationResolved(selectedEvent.value)) return
  if (!payload.run_id || !payload.confirmation_id) return
  resolving.value[payload.confirmation_id] = true
  try {
    await runsApi.resolveConfirmation(payload.run_id, payload.confirmation_id, {
      approved,
      reason: approved ? '前端批准执行' : '前端拒绝执行',
    })
    message.success(approved ? '已批准工具执行' : '已拒绝工具执行')
    eventDrawerOpen.value = false
  } finally {
    resolving.value[payload.confirmation_id] = false
  }
}

function applyAgentDefaults() {
  reactForm.executor_agent_id =
    executorAgents.value.find((item) => item.agent_id === 'default_executor')?.agent_id ||
    executorAgents.value[0]?.agent_id ||
    reactForm.executor_agent_id
  planForm.planner_agent_id =
    plannerAgents.value.find((item) => item.agent_id === 'default_planner')?.agent_id ||
    plannerAgents.value[0]?.agent_id ||
    planForm.planner_agent_id
  const defaultExecutor =
    executorAgents.value.find((item) => item.agent_id === 'default_executor')?.agent_id ||
    executorAgents.value[0]?.agent_id
  planForm.executor_agent_ids = defaultExecutor ? [defaultExecutor] : planForm.executor_agent_ids
  planForm.context_id =
    stepContexts.value.find((item) => item.context_id === 'default_step')?.context_id ||
    stepContexts.value[0]?.context_id ||
    planForm.context_id
}

onMounted(async () => {
  await Promise.all([
    conversations.fetchConversations(),
    agents.fetchAgents(),
    contexts.fetchContexts(),
  ])
  applyAgentDefaults()
  if (conversations.items[0]) {
    await conversations.selectConversation(conversations.items[0].conversation_id)
    const runId = latestMessageRunId.value
    if (runId) activateRun(runId)
  }
})
</script>

<template>
  <section class="chat-shell agent-workbench" :class="{ 'rail-collapsed': conversationRailCollapsed }">
    <aside class="conversation-rail agent-rail" :class="{ collapsed: conversationRailCollapsed }">
      <button class="rail-toggle" type="button" @click="conversationRailCollapsed = !conversationRailCollapsed">
        <MenuUnfoldOutlined v-if="conversationRailCollapsed" />
        <MenuFoldOutlined v-else />
      </button>

      <template v-if="conversationRailCollapsed">
        <a-tooltip title="展开会话">
          <button class="rail-avatar" type="button" @click="conversationRailCollapsed = false">
            {{ currentInitial() }}
          </button>
        </a-tooltip>
        <a-tooltip title="新建会话">
          <a-button shape="circle" type="primary" size="small" @click="conversations.createConversation({ title: '新会话' })">
            <CommentOutlined />
          </a-button>
        </a-tooltip>
        <a-tooltip title="移动端会话抽屉">
          <a-button class="mobile-rail-open" shape="circle" size="small" @click="conversationDrawerOpen = true">
            <AppstoreOutlined />
          </a-button>
        </a-tooltip>
      </template>

      <template v-else>
        <div class="rail-head">
          <h2>会话</h2>
          <a-button size="small" type="primary" @click="conversations.createConversation({ title: '新会话' })">
            新建
          </a-button>
        </div>
        <a-list :data-source="conversations.items" :loading="conversations.loading">
          <template #renderItem="{ item }">
            <a-list-item
              class="conversation-item"
              :class="{ active: item.conversation_id === conversations.current?.conversation_id }"
              @click="selectConversation(item.conversation_id)"
            >
              <a-list-item-meta :title="item.title" :description="item.conversation_id" />
              <a-button danger size="small" @click.stop="confirmDeleteConversation(item)">删除</a-button>
            </a-list-item>
          </template>
        </a-list>
      </template>
    </aside>

    <main class="chat-main panel-card agent-chat-main" style="max-height: 150vh;">
      <div class="chat-topbar agent-chat-topbar">
        <div>
          <span class="eyebrow">Agent Chat</span>
          <h1>{{ conversations.current?.title || '未选择会话' }}</h1>
          <div class="run-capsule-row">
            <a-tag :color="activeRunId ? 'blue' : 'default'">Run {{ shortId(activeRunId) }}</a-tag>
            <a-tag>{{ runStats.events }} events</a-tag>
            <a-tag :color="runStats.failed ? 'red' : 'green'">{{ runStats.failed }} failed</a-tag>
            <a-tag :color="runStats.pending ? 'orange' : 'default'">{{ runStats.pending }} confirmations</a-tag>
          </div>
        </div>
        <a-space wrap>
          <a-button class="mobile-conversation-button" @click="conversationDrawerOpen = true">
            会话
          </a-button>
          <a-tag :color="chatMode === 'react' ? 'blue' : 'purple'">{{ modeConfigSummary }}</a-tag>
          <a-button @click="configModalOpen = true">模型配置</a-button>
          <a-button danger :disabled="!conversations.current" @click="confirmDeleteConversation()">删除会话</a-button>
          <a-button danger :loading="cancelingRun" :disabled="!canCancelActiveRun" @click="cancelActiveRun">
            中断 Run
          </a-button>
        </a-space>
      </div>

      <div ref="listRef" class="message-list agent-message-list">
        <a-empty
          v-if="!mainChatItems.length"
          description="还没有消息或事件"
        />

        <template v-for="item in mainChatItems" :key="item.key">
          <div
            v-if="item.kind === 'conversation'"
            class="message-bubble"
            :class="item.message.role"
          >
            <div class="message-meta-row">
              <a-tag>{{ item.message.role }}</a-tag>
              <a-button
                v-if="item.message.run_id"
                size="small"
                type="link"
                @click="activateRun(item.message.run_id)"
              >
                Run {{ shortId(item.message.run_id) }}
              </a-button>
            </div>
            <p>{{ item.message.content }}</p>
            <small>{{ item.message.message_id }}</small>
          </div>

          <div
            v-else-if="item.kind === 'agent-output'"
            class="message-bubble agent-output-bubble"
            :class="item.output.tone"
            @click="openEvent(item.event)"
          >
            <div class="message-meta-row">
              <a-tag :color="eventColor(item.event.name)">{{ item.output.role }}</a-tag>
              <a-tag>{{ item.output.title }}</a-tag>
              <span>{{ eventTime(item.event) }}</span>
            </div>
            <p>{{ item.output.content }}</p>
            <small>{{ item.output.meta }}</small>
          </div>

          <div
            v-else
            class="message-bubble event-bubble"
            :class="eventTone(item.event.name)"
            @click="openEvent(item.event)"
          >
            <div class="event-bubble-head">
              <a-tag :color="eventColor(item.event.name)">{{ item.event.name }}</a-tag>
              <span>{{ eventTime(item.event) }}</span>
            </div>
            <strong>{{ eventSummary(item.event) }}</strong>
            <JsonBlock class="event-bubble-preview" :value="payloadPreview(item.event)" />
          </div>
        </template>
      </div>

      <div class="chat-composer agent-composer">
        <a-textarea v-model:value="input" :rows="3" placeholder="输入给 Agent 的任务..." />
      </div>
      <div style="margin-top: 16px;justify-self: end;">
        <a-button type="primary" @click="sendMessage" :disabled="!input.trim()">发送</a-button>
      </div>

    </main>

    <aside class="event-side executor-workbench">
      <a-card class="panel-card executor-toolbar" :bordered="false">
        <div class="card-title-row">
          <span>执行者工作台</span>
          <a-tag :color="executorEvents.length ? 'blue' : 'default'">{{ executorEvents.length }} events</a-tag>
        </div>
        <a-segmented
          v-model:value="executorOutputPlacement"
          class="executor-placement-switch"
          :options="[
            { label: '输出在右侧', value: 'side' },
            { label: '合并到主聊天', value: 'main' },
          ]"
        />
        <a-input-search
          v-model:value="activeRunId"
          enter-button="连接"
          placeholder="Run ID"
          @search="activateRun(activeRunId)"
        />
        <a-select v-model:value="selectedExecutor" class="mt-12" style="width: 100%" placeholder="executor">
          <a-select-option value="">全部执行者</a-select-option>
          <a-select-option v-for="id in executorOptions" :key="id" :value="id">
            {{ agentLabel(id) }}
          </a-select-option>
        </a-select>
      </a-card>

      <a-card class="panel-card embedded-slot executor-inspector" :bordered="false">
        <a-segmented
          v-model:value="executorPanelTab"
          class="executor-panel-switch"
          :options="[
            { label: '输出', value: 'outputs' },
            { label: '事件', value: 'events' },
            { label: 'Payload', value: 'payload' },
          ]"
        />

        <div v-if="executorPanelTab === 'outputs'" ref="executorOutputRef" class="executor-output-list">
          <a-empty
            v-if="!visibleExecutorOutputEvents.length"
            description="执行者输出默认显示在这里"
          />
          <article
            v-for="event in visibleExecutorOutputEvents"
            :key="event.event_id || `${event.name}-${event.created_at}`"
            class="executor-output-card"
            :class="agentOutputMessageFromEvent(event).tone"
            @click="openEvent(event)"
          >
            <div class="message-meta-row">
              <a-tag :color="eventColor(event.name)">{{ agentOutputMessageFromEvent(event).title }}</a-tag>
              <span>{{ eventTime(event) }}</span>
            </div>
            <p>{{ agentOutputMessageFromEvent(event).content }}</p>
            <small>{{ agentOutputMessageFromEvent(event).meta }}</small>
          </article>
        </div>

        <div v-else-if="executorPanelTab === 'events'" ref="executorEventsRef" class="executor-events-scroll">
          <ExecutorEventPanel
            :events="executorEvents"
            :executor-id="selectedExecutor"
            title="Executor / Tool 事件"
            selectable
            @select="openEvent"
          />
        </div>

        <JsonBlock
          v-else
          class="executor-payload-block"
          :value="latestExecutorPayload"
        />
        <a-button class="mt-12" block @click="openEmbeddedRoute" :disabled="!activeRunId">
          新窗口查看该面板
        </a-button>
      </a-card>

      <a-card class="panel-card orchestrator-mini" title="编排时间线" :bordered="false">
        <EventTimeline
          :events="orchestratorEvents"
          compact
          selectable
          @select="openEvent"
        />
      </a-card>
    </aside>

    <a-drawer
      v-model:open="eventDrawerOpen"
      width="560"
      class="event-inspector-drawer"
      placement="right"
      :title="selectedEvent?.name || '事件详情'"
    >
      <template v-if="selectedEvent">
        <a-space class="mb-16" wrap>
          <a-tag :color="eventColor(selectedEvent.name)">{{ selectedEvent.name }}</a-tag>
          <a-tag>{{ eventTime(selectedEvent) }}</a-tag>
        </a-space>
        <a-descriptions :column="1" size="small" bordered>
          <a-descriptions-item v-for="item in selectedEventMeta" :key="item.label" :label="item.label">
            {{ item.value }}
          </a-descriptions-item>
        </a-descriptions>
        <a-space v-if="isConfirmationRequest(selectedEvent)" class="confirmation-actions mt-16">
          <a-button
            type="primary"
            :loading="resolving[selectedEvent.payload.confirmation_id]"
            :disabled="isConfirmationResolved(selectedEvent)"
            @click="resolveSelectedConfirmation(true)"
          >
            批准
          </a-button>
          <a-button
            danger
            :loading="resolving[selectedEvent.payload.confirmation_id]"
            :disabled="isConfirmationResolved(selectedEvent)"
            @click="resolveSelectedConfirmation(false)"
          >
            拒绝
          </a-button>
        </a-space>
        <JsonBlock class="mt-16" :value="selectedEvent.payload || {}" />
      </template>
    </a-drawer>

    <a-modal
      v-model:open="configModalOpen"
      title="Agent 模型配置"
      width="760px"
      ok-text="完成"
      cancel-text="关闭"
      @ok="configModalOpen = false"
    >
      <a-form layout="vertical">
        <a-form-item label="运行模式">
          <a-segmented
            v-model:value="chatMode"
            :options="[
              { label: 'React 单 Agent', value: 'react' },
              { label: 'Plan 编排', value: 'plan' },
            ]"
          />
        </a-form-item>

        <template v-if="chatMode === 'react'">
          <a-form-item label="Executor Agent">
            <a-select
              v-model:value="reactForm.executor_agent_id"
              show-search
              option-filter-prop="label"
              placeholder="选择 executor agent"
            >
              <a-select-option
                v-for="agent in executorAgents"
                :key="agent.agent_id"
                :value="agent.agent_id"
                :label="`${agent.name} ${agent.agent_id}`"
              >
                {{ agent.name }} · {{ agent.agent_id }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </template>

        <template v-else>
          <a-form-item label="Planner Agent">
            <a-select
              v-model:value="planForm.planner_agent_id"
              show-search
              option-filter-prop="label"
              placeholder="选择 planner"
            >
              <a-select-option
                v-for="agent in plannerAgents"
                :key="agent.agent_id"
                :value="agent.agent_id"
                :label="`${agent.name} ${agent.agent_id}`"
              >
                {{ agent.name }} · {{ agent.agent_id }}
              </a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item label="Executor Agents">
            <a-select
              v-model:value="planForm.executor_agent_ids"
              mode="multiple"
              show-search
              option-filter-prop="label"
              placeholder="选择一个或多个 executor"
            >
              <a-select-option
                v-for="agent in executorAgents"
                :key="agent.agent_id"
                :value="agent.agent_id"
                :label="`${agent.name} ${agent.agent_id}`"
              >
                {{ agent.name }} · {{ agent.agent_id }}
              </a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item label="Step Context">
            <a-select
              v-model:value="planForm.context_id"
              show-search
              option-filter-prop="label"
              placeholder="选择 step context"
            >
              <a-select-option
                v-for="context in stepContexts"
                :key="context.context_id"
                :value="context.context_id"
                :label="`${context.name} ${context.context_id}`"
              >
                {{ context.name }} · {{ context.context_id }}
              </a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item label="Max Replan Rounds">
            <a-input-number v-model:value="planForm.max_replan_rounds" :min="0" />
          </a-form-item>
        </template>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="conversationDrawerOpen"
      title="会话"
      placement="left"
      width="320"
    >
      <a-button block type="primary" class="mb-16" @click="conversations.createConversation({ title: '新会话' })">
        新建会话
      </a-button>
      <a-list :data-source="conversations.items" :loading="conversations.loading">
        <template #renderItem="{ item }">
          <a-list-item
            class="conversation-item"
            :class="{ active: item.conversation_id === conversations.current?.conversation_id }"
            @click="selectConversation(item.conversation_id)"
          >
            <a-list-item-meta :title="item.title" :description="item.conversation_id" />
            <a-button danger size="small" @click.stop="confirmDeleteConversation(item)">删除</a-button>
          </a-list-item>
        </template>
      </a-list>
    </a-drawer>
  </section>
</template>
