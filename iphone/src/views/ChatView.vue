<script setup>
// 移动端聊天页：全屏推入（无 tabbar）。
// 桌面端 ChatView 的「消息流 + 运行时间线 + 产物卡 + 审批」在小屏上拆为：
//   主体 = 纯消息流（产物收成 chip）；运行细节 = 底部抽屉时间线；
//   产物 = 全屏预览；危险命令审批 = 输入框上方浮动卡片。
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { renderMarkdown } from '@/utils/markdown'
import { eventTitle, eventContent, eventActor, isArtifactEvent } from '@/utils/runtimeEvents'
import ArtifactPreview from '@/components/ArtifactPreview.vue'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()

const draft = ref('')
const mentions = ref([])
const errorText = ref('')
const listRef = ref(null)
const inputRef = ref(null)
const previewArtifact = ref(null)
const timelineOpen = ref(false)
const mentionSheetOpen = ref(false)
const cancelling = ref(false)
const loading = ref(true)

const isGroup = computed(() => route.name === 'chat-group')

const headerTitle = computed(() => {
  if (isGroup.value) return chat.room?.title || '群聊'
  const agent = chat.agentById[chat.conversation?.agent_id]
  return chat.conversation?.title || agent?.name || '会话'
})

const headerAgent = computed(() => chat.agentById[chat.conversation?.agent_id] || null)

const memberAgents = computed(() => {
  if (!isGroup.value) return []
  return (chat.room?.member_agent_ids || [])
    .map((agentId) => chat.agentById[agentId])
    .filter(Boolean)
})

// 正在运行的回复：dm 看 user 消息 running；group 看带 run_id 的 running 消息
const runningMessage = computed(() =>
  [...chat.messages].reverse().find((item) => item.status === 'running'),
)

// 运行态必须用 /runs/active 交叉验证：消息的 running 状态落在库里，但执行任务在后端内存，
// 后端重启后库里会残留 running——只信消息状态会永远误显示「正在运行」。
// 刚触发的回复给 20s 宽限期（activeRuns 轮询有延迟，避免发送瞬间状态条闪烁）。
const nowSec = ref(Math.floor(Date.now() / 1000))
let nowTimer = null
let runsPollTimer = null

const isRunning = computed(() => {
  const msg = runningMessage.value
  if (!msg) return false
  const age = nowSec.value - (msg.updated_at || msg.created_at || 0)
  if (age < 20) return true
  if (isGroup.value) {
    const roomId = chat.room?.room_id
    return chat.activeRuns.some((run) => run.room_id === roomId || (msg.run_id && run.run_id === msg.run_id))
  }
  const conversationId = chat.conversation?.conversation_id
  return chat.activeRuns.some(
    (run) => run.run_id === msg.message_id || (run.kind === 'dm_reply' && run.conversation_id === conversationId),
  )
})

const headerSubtitle = computed(() => {
  if (isRunning.value) return '智能体正在运行…'
  if (isGroup.value) return `${memberAgents.value.length} 位成员`
  return headerAgent.value?.agent_type === 'executor' ? '在线' : ''
})

// ── 消息渲染 ────────────────────────────────────────────
function senderName(item) {
  if (item.sender_type === 'user') return '我'
  if (item.sender_type === 'system') return '系统'
  return chat.agentById[item.sender_id]?.name || item.sender_id
}

function senderAvatar(item) {
  if (item.sender_type !== 'agent') return ''
  return chat.agentById[item.sender_id]?.metadata?.avatar_url || ''
}

function textParts(item) {
  return (item.content_parts || []).filter((part) => part.type === 'text' && part.text)
}

function artifactParts(item) {
  return (item.content_parts || [])
    .filter((part) => part.type !== 'text')
    .map((part) => part.metadata?.artifact || part)
}

const ARTIFACT_ICON = {
  document: '📄',
  message: '💬',
  image: '🖼️',
  diff: '🧩',
  web: '🌐',
  video: '🎬',
  deploy: '🚀',
}

function artifactLabel(artifact) {
  return artifact?.title || artifact?.file_path || artifact?.type || '产物'
}

function formatTime(ts) {
  if (!ts) return ''
  const date = new Date(ts * 1000)
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  const hm = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  if (sameDay) return hm
  return `${date.getMonth() + 1}月${date.getDate()}日 ${hm}`
}

// 时间分隔条：相邻消息间隔 > 10 分钟才显示
function showTimeDivider(index) {
  if (index === 0) return true
  const prev = chat.messages[index - 1]
  const curr = chat.messages[index]
  return (curr.created_at || 0) - (prev.created_at || 0) > 600
}

// ── 运行时间线（底部抽屉） ──────────────────────────────
const TIMELINE_HIDDEN = new Set(['llm.delta', 'agent.delta', 'llm.streaming'])
const timelineEvents = computed(() =>
  chat.events
    .filter((event) => !TIMELINE_HIDDEN.has(event.name))
    .slice(-60)
    .map((event) => ({
      id: event.event_id,
      name: event.name,
      actor: eventActor(event, (agentId) => chat.agentById[agentId]?.name || agentId),
      title: eventTitle(event),
      content: String(eventContent(event) || '').slice(0, 160),
      isArtifact: isArtifactEvent(event),
    })),
)

// ── 滚动 ────────────────────────────────────────────────
async function scrollToBottom(smooth = false) {
  await nextTick()
  const el = listRef.value
  if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

function nearBottom() {
  const el = listRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 140
}

async function handleScroll() {
  const el = listRef.value
  if (!el || el.scrollTop > 60 || !chat.hasMoreMessages || chat.loadingOlder) return
  const beforeHeight = el.scrollHeight
  const added = await chat.loadOlderMessages()
  if (added > 0) {
    await nextTick()
    el.scrollTop = el.scrollHeight - beforeHeight
  }
}

watch(
  () => chat.messages.length,
  () => {
    if (nearBottom()) scrollToBottom(true)
  },
)

// ── 发送 / 中断 ─────────────────────────────────────────
async function send() {
  const text = draft.value.trim()
  if (!text || chat.sending) return
  errorText.value = ''
  try {
    await chat.sendText(text, isGroup.value ? [...mentions.value] : [])
    draft.value = ''
    mentions.value = []
    await scrollToBottom(true)
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '发送失败，请重试'
  }
}

async function interrupt() {
  const target = runningMessage.value
  if (!target || cancelling.value) return
  cancelling.value = true
  errorText.value = ''
  try {
    if (isGroup.value && target.run_id) {
      await chat.cancelGroupRun(target.run_id)
    } else if (!isGroup.value) {
      // dm：中断触发回复的 user 消息（running 的就是它）
      const userMessage = [...chat.messages]
        .reverse()
        .find((item) => item.sender_type === 'user' && item.status === 'running')
      if (userMessage) await chat.cancelDmReply(userMessage.message_id)
    }
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '中断失败'
  } finally {
    cancelling.value = false
  }
}

function insertMention(agent) {
  if (!mentions.value.includes(agent.agent_id)) mentions.value.push(agent.agent_id)
  draft.value = `${draft.value}${draft.value && !draft.value.endsWith(' ') ? ' ' : ''}@${agent.name} `
  mentionSheetOpen.value = false
  nextTick(() => inputRef.value?.focus?.())
}

function autoGrow(event) {
  const el = event.target
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 116)}px`
}

// ── 审批卡片 ────────────────────────────────────────────
async function resolveConfirm(item, approved) {
  try {
    await chat.resolveConfirmation(item.run_id, item.confirmation_id, approved)
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '审批提交失败'
  }
}

function confirmArgsPreview(item) {
  const args = item.arguments ?? item.args ?? {}
  const text = typeof args === 'string' ? args : JSON.stringify(args, null, 0)
  return text.length > 120 ? `${text.slice(0, 120)}…` : text
}

// ── 生命周期 ────────────────────────────────────────────
onMounted(async () => {
  loading.value = true
  try {
    if (!chat.agents.length) await chat.bootstrap()
    if (isGroup.value) {
      await chat.openGroup(route.params.roomId, route.params.conversationId || '')
    } else {
      await chat.openDm(route.params.conversationId)
    }
    await scrollToBottom()
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '会话加载失败'
  } finally {
    loading.value = false
  }
  // 运行态交叉验证数据源：进入即拉一次，之后 4s 轮询（silentHttp，不打扰）
  chat.fetchActiveRuns().catch(() => {})
  runsPollTimer = setInterval(() => chat.fetchActiveRuns().catch(() => {}), 4000)
  nowTimer = setInterval(() => {
    nowSec.value = Math.floor(Date.now() / 1000)
  }, 5000)
})

onUnmounted(() => {
  if (runsPollTimer) clearInterval(runsPollTimer)
  if (nowTimer) clearInterval(nowTimer)
  chat.closeChat()
})

function goBack() {
  router.back()
}
</script>

<template>
  <div class="chat-page">
    <!-- 顶部毛玻璃栏 -->
    <header class="glass-bar chat-head">
      <button class="head-back" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="m15 18-6-6 6-6" />
        </svg>
      </button>
      <div class="head-id">
        <div class="avatar head-avatar">
          <img v-if="headerAgent?.metadata?.avatar_url" :src="headerAgent.metadata.avatar_url" alt="" />
          <template v-else>{{ (headerTitle || 'A').slice(0, 1).toUpperCase() }}</template>
        </div>
        <div class="head-text">
          <strong>{{ headerTitle }}</strong>
          <span :class="{ 'head-running': isRunning }">
            <span v-if="isRunning" class="dot dot--running"></span>
            {{ headerSubtitle }}
          </span>
        </div>
      </div>
      <button class="head-timeline" :class="{ on: timelineOpen }" title="运行过程" @click="timelineOpen = !timelineOpen">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      </button>
    </header>

    <!-- 消息流 -->
    <div ref="listRef" class="msg-list" @scroll.passive="handleScroll">
      <div v-if="chat.loadingOlder" class="older-loading">加载更早的消息…</div>
      <div v-if="loading" class="empty"><span class="empty-icon">⋯</span><span>加载中</span></div>
      <div v-else-if="!chat.messages.length" class="empty">
        <span class="empty-icon">💬</span>
        <span>还没有消息，说点什么吧</span>
      </div>

      <template v-for="(item, index) in chat.messages" :key="item.message_id">
        <div v-if="showTimeDivider(index)" class="time-divider">{{ formatTime(item.created_at) }}</div>

        <!-- 系统消息 -->
        <div v-if="item.sender_type === 'system'" class="sys-chip">
          {{ textParts(item)[0]?.text?.slice(0, 80) || '系统消息' }}
        </div>

        <!-- 普通气泡 -->
        <div v-else class="msg-row" :class="{ mine: item.sender_type === 'user' }">
          <div v-if="item.sender_type === 'agent'" class="avatar msg-avatar">
            <img v-if="senderAvatar(item)" :src="senderAvatar(item)" alt="" />
            <template v-else>{{ senderName(item).slice(0, 1).toUpperCase() }}</template>
          </div>
          <div class="msg-col">
            <span v-if="isGroup && item.sender_type === 'agent'" class="msg-sender">{{ senderName(item) }}</span>
            <div class="bubble" :class="item.sender_type === 'user' ? 'bubble--mine' : 'bubble--agent'">
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div
                v-for="(part, pi) in textParts(item)"
                :key="`t-${pi}`"
                class="md-body bubble-md"
                v-html="renderMarkdown(part.text)"
              ></div>
              <!-- 产物 chips -->
              <button
                v-for="(artifact, ai) in artifactParts(item)"
                :key="`a-${ai}`"
                class="artifact-chip"
                @click="previewArtifact = artifact"
              >
                <span class="chip-icon">{{ ARTIFACT_ICON[(artifact.type || 'message').toLowerCase()] || '📦' }}</span>
                <span class="chip-label">{{ artifactLabel(artifact) }}</span>
                <svg class="chip-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </button>
              <span v-if="item.status === 'cancelled'" class="bubble-state">已中断</span>
            </div>
          </div>
        </div>
      </template>

      <!-- 运行中 typing 指示 -->
      <div v-if="isRunning" class="msg-row">
        <div class="avatar msg-avatar typing-avatar">
          <template v-if="headerAgent">{{ (headerAgent.name || 'A').slice(0, 1).toUpperCase() }}</template>
          <template v-else>A</template>
        </div>
        <div class="bubble bubble--agent typing-bubble">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    </div>

    <!-- 待审批浮动卡片 -->
    <div v-if="chat.humanConfirmations.length" class="confirm-stack">
      <div v-for="item in chat.humanConfirmations" :key="item.confirmation_id" class="confirm-card rise-in">
        <div class="confirm-head">
          <span class="confirm-icon">⚠️</span>
          <strong>等待你的批准</strong>
        </div>
        <p class="confirm-tool">{{ item.tool_name || '工具调用' }}</p>
        <code class="confirm-args">{{ confirmArgsPreview(item) }}</code>
        <div class="confirm-actions">
          <button class="btn-danger confirm-btn" @click="resolveConfirm(item, false)">拒绝</button>
          <button class="btn-ghost confirm-btn confirm-allow" @click="resolveConfirm(item, true)">允许执行</button>
        </div>
      </div>
    </div>

    <!-- 错误条 -->
    <div v-if="errorText" class="error-bar" @click="errorText = ''">{{ errorText }}</div>

    <!-- 运行中状态条 -->
    <div v-if="isRunning" class="run-strip">
      <span class="dot dot--running"></span>
      <span class="run-strip-text">智能体正在运行…</span>
      <button class="run-strip-detail" @click="timelineOpen = true">过程</button>
      <button class="run-strip-stop" :disabled="cancelling" @click="interrupt">
        {{ cancelling ? '中断中…' : '中断' }}
      </button>
    </div>

    <!-- 输入栏 -->
    <footer class="composer">
      <button v-if="isGroup" class="composer-at" @click="mentionSheetOpen = true">@</button>
      <textarea
        ref="inputRef"
        v-model="draft"
        rows="1"
        class="composer-input"
        :placeholder="isGroup ? '发消息，@ 可指定 agent' : '发消息…'"
        @input="autoGrow"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button class="composer-send" :disabled="!draft.trim() || chat.sending" @click="send">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m22 2-7 20-4-9-9-4Z" />
          <path d="M22 2 11 13" />
        </svg>
      </button>
    </footer>

    <!-- 群成员 @ 选择 sheet -->
    <Teleport to="body">
      <div v-if="mentionSheetOpen" class="sheet-mask" @click.self="mentionSheetOpen = false">
        <div class="sheet rise-in">
          <div class="sheet-grip"></div>
          <h3 class="sheet-title">提及成员</h3>
          <button v-for="agent in memberAgents" :key="agent.agent_id" class="sheet-row" @click="insertMention(agent)">
            <div class="avatar sheet-avatar">
              <img v-if="agent.metadata?.avatar_url" :src="agent.metadata.avatar_url" alt="" />
              <template v-else>{{ (agent.name || 'A').slice(0, 1).toUpperCase() }}</template>
            </div>
            <span class="sheet-name">{{ agent.name }}</span>
            <span class="sheet-kind">{{ agent.agent_type === 'planner' ? '规划' : '执行' }}</span>
          </button>
        </div>
      </div>
    </Teleport>

    <!-- 运行时间线 sheet -->
    <Teleport to="body">
      <div v-if="timelineOpen" class="sheet-mask" @click.self="timelineOpen = false">
        <div class="sheet sheet--tall rise-in">
          <div class="sheet-grip"></div>
          <h3 class="sheet-title">运行过程</h3>
          <div class="timeline">
            <div v-if="!timelineEvents.length" class="empty">
              <span class="empty-icon">📡</span>
              <span>本次会话暂无运行事件</span>
            </div>
            <div v-for="event in timelineEvents" :key="event.id" class="tl-row">
              <span class="tl-dot" :class="{ 'tl-dot--artifact': event.isArtifact }"></span>
              <div class="tl-body">
                <div class="tl-head">
                  <strong>{{ event.title || event.name }}</strong>
                  <span v-if="event.actor" class="tl-actor">{{ event.actor }}</span>
                </div>
                <p v-if="event.content" class="tl-content">{{ event.content }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 产物全屏预览 -->
    <ArtifactPreview v-if="previewArtifact" :artifact="previewArtifact" @close="previewArtifact = null" />
  </div>
</template>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

/* ── 头部 ── */
.chat-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: calc(var(--safe-top) + 10px) 12px 10px;
}

.head-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-pill);
  color: var(--accent);
}

.head-back svg {
  width: 22px;
  height: 22px;
}

.head-id {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.head-avatar {
  width: 38px;
  height: 38px;
  font-size: 16px;
}

.head-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.head-text strong {
  font-size: 16px;
  letter-spacing: -0.2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.head-text span {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--muted);
}

.head-running {
  color: var(--green) !important;
  font-weight: 700;
}

.head-timeline {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-pill);
  color: var(--muted);
  background: rgba(15, 23, 42, 0.04);
}

.head-timeline.on {
  color: var(--accent);
  background: var(--accent-soft);
}

.head-timeline svg {
  width: 18px;
  height: 18px;
}

/* ── 消息流 ── */
.msg-list {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 14px 14px 10px;
}

.older-loading {
  text-align: center;
  color: var(--muted-2);
  font-size: 12px;
  padding: 6px 0 10px;
}

.time-divider {
  width: fit-content;
  margin: 14px auto 10px;
  padding: 3px 12px;
  border-radius: var(--r-pill);
  background: rgba(15, 23, 42, 0.045);
  color: var(--muted-2);
  font-size: 11px;
  font-weight: 600;
}

.sys-chip {
  margin: 8px auto;
  max-width: 86%;
  width: fit-content;
  padding: 6px 14px;
  border-radius: var(--r-pill);
  background: rgba(15, 23, 42, 0.05);
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}

.msg-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin-bottom: 12px;
}

.msg-row.mine {
  flex-direction: row-reverse;
}

.msg-avatar {
  width: 30px;
  height: 30px;
  font-size: 13px;
  margin-bottom: 2px;
}

.msg-col {
  display: flex;
  flex-direction: column;
  max-width: 82%;
  min-width: 0;
}

.mine .msg-col {
  align-items: flex-end;
}

.msg-sender {
  font-size: 11px;
  color: var(--muted);
  margin: 0 0 3px 4px;
  font-weight: 700;
}

.bubble {
  position: relative;
  padding: 10px 13px;
  font-size: 14.5px;
  line-height: 1.55;
  word-break: break-word;
}

.bubble--agent {
  background: var(--surface);
  border: 0.5px solid rgba(15, 23, 42, 0.06);
  border-radius: 4px var(--r-md) var(--r-md) var(--r-md);
  box-shadow: var(--shadow-card);
  animation: rise-in 0.22s ease both;
}

.bubble--mine {
  background: var(--accent-grad);
  color: #fff;
  border-radius: var(--r-md) 4px var(--r-md) var(--r-md);
  box-shadow: var(--shadow-accent);
}

.bubble-md {
  font-size: 14.5px;
}

.bubble--mine .bubble-md :deep(a) {
  color: #dbe7ff;
  text-decoration: underline;
}

.bubble--mine .bubble-md :deep(code) {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

.bubble-state {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  opacity: 0.7;
}

/* 产物 chip */
.artifact-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-top: 8px;
  padding: 9px 11px;
  border-radius: var(--r-sm);
  background: rgba(15, 23, 42, 0.045);
  text-align: left;
  transition: transform 0.12s ease;
}

.artifact-chip:active {
  transform: scale(0.97);
}

.bubble--mine .artifact-chip {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}

.chip-icon {
  font-size: 16px;
}

.chip-label {
  flex: 1;
  font-size: 13px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-arrow {
  width: 14px;
  height: 14px;
  opacity: 0.5;
}

/* typing */
.typing-bubble {
  display: flex;
  gap: 5px;
  padding: 14px 16px;
}

.typing-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--muted-2);
  animation: typing 1.2s ease-in-out infinite;
}

.typing-dot:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes typing {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

/* ── 审批浮动卡 ── */
.confirm-stack {
  padding: 0 14px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.confirm-card {
  background: var(--surface);
  border: 1.5px solid rgba(217, 119, 6, 0.35);
  border-radius: var(--r-md);
  padding: 12px 14px;
  box-shadow: var(--shadow-float);
}

.confirm-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  color: var(--amber);
}

.confirm-tool {
  margin-top: 6px;
  font-size: 13.5px;
  font-weight: 800;
}

.confirm-args {
  display: block;
  margin-top: 5px;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  background: rgba(15, 23, 42, 0.05);
  font-family: ui-monospace, Menlo, monospace;
  font-size: 11.5px;
  color: var(--ink-2);
  word-break: break-all;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.confirm-btn {
  flex: 1;
  height: 38px;
}

.confirm-allow {
  background: var(--green-soft);
  color: var(--green);
}

/* ── 错误条 / 运行条 ── */
.error-bar {
  margin: 0 14px 8px;
  padding: 9px 13px;
  border-radius: var(--r-sm);
  background: var(--red-soft);
  color: var(--red);
  font-size: 13px;
}

.run-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 14px 8px;
  padding: 8px 13px;
  border-radius: var(--r-pill);
  background: var(--surface);
  box-shadow: var(--shadow-card);
}

.run-strip-text {
  flex: 1;
  font-size: 12.5px;
  color: var(--green);
  font-weight: 700;
}

.run-strip-detail {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--accent);
  padding: 4px 10px;
  border-radius: var(--r-pill);
  background: var(--accent-soft);
}

.run-strip-stop {
  font-size: 12.5px;
  font-weight: 800;
  color: var(--red);
  padding: 4px 12px;
  border-radius: var(--r-pill);
  background: var(--red-soft);
}

/* ── 输入栏 ── */
.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 12px calc(var(--safe-bottom) + 10px);
  background: var(--surface-glass);
  backdrop-filter: blur(18px) saturate(1.4);
  -webkit-backdrop-filter: blur(18px) saturate(1.4);
  border-top: 0.5px solid var(--line);
}

.composer-at {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: var(--r-pill);
  background: rgba(15, 23, 42, 0.05);
  color: var(--muted);
  font-size: 17px;
  font-weight: 800;
  flex: none;
}

.composer-input {
  flex: 1;
  max-height: 116px;
  padding: 9px 14px;
  border-radius: 19px;
  background: rgba(15, 23, 42, 0.05);
  border: 1.5px solid transparent;
  font-size: 15px;
  line-height: 1.4;
  resize: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.composer-input:focus {
  border-color: var(--accent);
  background: var(--surface);
}

.composer-send {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: var(--r-pill);
  background: var(--accent-grad);
  color: #fff;
  box-shadow: var(--shadow-accent);
  flex: none;
  transition: transform 0.12s ease, opacity 0.12s ease;
}

.composer-send:active {
  transform: scale(0.92);
}

.composer-send:disabled {
  opacity: 0.4;
  box-shadow: none;
}

.composer-send svg {
  width: 17px;
  height: 17px;
}

/* ── bottom sheets ── */
.sheet-mask {
  position: fixed;
  inset: 0;
  z-index: 90;
  background: rgba(15, 23, 42, 0.4);
  display: flex;
  align-items: flex-end;
}

.sheet {
  width: 100%;
  max-height: 62%;
  background: var(--bg);
  border-radius: 24px 24px 0 0;
  padding: 8px 16px calc(var(--safe-bottom) + 16px);
  overflow-y: auto;
}

.sheet--tall {
  height: 72%;
  max-height: 72%;
}

.sheet-grip {
  width: 38px;
  height: 4.5px;
  border-radius: var(--r-pill);
  background: rgba(15, 23, 42, 0.15);
  margin: 4px auto 12px;
}

.sheet-title {
  font-size: 17px;
  font-weight: 800;
  margin-bottom: 12px;
}

.sheet-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 6px;
  border-radius: var(--r-md);
  text-align: left;
}

.sheet-row:active {
  background: rgba(15, 23, 42, 0.04);
}

.sheet-avatar {
  width: 36px;
  height: 36px;
  font-size: 15px;
}

.sheet-name {
  flex: 1;
  font-size: 15px;
  font-weight: 700;
}

.sheet-kind {
  font-size: 12px;
  color: var(--muted);
  padding: 3px 10px;
  border-radius: var(--r-pill);
  background: rgba(15, 23, 42, 0.05);
}

/* 时间线 */
.timeline {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tl-row {
  display: flex;
  gap: 10px;
  padding: 8px 2px;
}

.tl-dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--muted-2);
}

.tl-dot--artifact {
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.tl-body {
  flex: 1;
  min-width: 0;
}

.tl-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.tl-head strong {
  font-size: 13px;
}

.tl-actor {
  font-size: 11px;
  color: var(--muted);
}

.tl-content {
  margin-top: 2px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
  word-break: break-word;
}
</style>
