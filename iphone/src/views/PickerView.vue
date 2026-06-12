<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { imApi } from '@/api/im'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()

const isAgentMode = computed(() => route.name === 'agent-conversations')
const agentId = computed(() => route.params.agentId || '')
const roomId = computed(() => route.params.roomId || '')

const loading = ref(true)
const creating = ref(false)
const createError = ref('')
const conversations = ref([])

// ── 工具 ───────────────────────────────────────────────────
function firstChar(name) {
  const trimmed = (name || '').trim()
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : '·'
}

function hueIndex(id) {
  let hash = 0
  for (const ch of String(id || '')) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return hash % 6
}

function clip(text, max) {
  const t = (text || '').trim()
  if (!t) return ''
  return t.length > max ? `${t.slice(0, max)}…` : t
}

function summarize(lastMessage) {
  const parts = lastMessage?.content_parts || []
  const part = parts.find((entry) => entry && typeof entry.text === 'string' && entry.text.trim())
  return clip(part?.text, 40)
}

function formatTime(ts) {
  if (!ts) return ''
  const date = new Date(ts * 1000)
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  if (sameDay) {
    const hh = String(date.getHours()).padStart(2, '0')
    const mm = String(date.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  }
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

// ── 实体名片数据 ───────────────────────────────────────────
const agent = computed(() => chat.agentById[agentId.value] || null)
const room = computed(() => chat.rooms.find((r) => r.room_id === roomId.value) || null)

const entityId = computed(() => (isAgentMode.value ? agentId.value : roomId.value))
const entityTitle = computed(() => {
  if (isAgentMode.value) return agent.value?.name || '智能体'
  return room.value?.title || '群聊'
})
const entityAvatarUrl = computed(() => (isAgentMode.value ? agent.value?.metadata?.avatar_url || '' : ''))
const entitySubtitle = computed(() => {
  if (isAgentMode.value) {
    const raw = agent.value?.description || agent.value?.metadata?.description || ''
    return clip(raw, 60) || '随时可以开始对话'
  }
  const ids = room.value?.member_agent_ids || []
  const names = ids
    .map((id) => chat.agentById[id]?.name)
    .filter(Boolean)
    .slice(0, 3)
  let line = `${ids.length} 位成员`
  if (names.length) line += ` · ${names.join('、')}`
  return line
})
const agentTypeMeta = computed(() =>
  agent.value?.agent_type === 'planner'
    ? { label: '规划', cls: 'chip-plan' }
    : { label: '执行', cls: 'chip-exec' },
)
const entityRunning = computed(() =>
  isAgentMode.value
    ? chat.runningAgentIds.has(agentId.value)
    : chat.runningRoomIds.has(roomId.value),
)

// ── 加载 ───────────────────────────────────────────────────
async function loadConversations() {
  const response = isAgentMode.value
    ? await imApi.agentConversations(agentId.value)
    : await imApi.roomConversations(roomId.value)
  conversations.value = (response?.items || []).slice().sort((a, b) => {
    const ta = a.last_message?.created_at || a.updated_at || 0
    const tb = b.last_message?.created_at || b.updated_at || 0
    return tb - ta
  })
}

// ── 交互 ───────────────────────────────────────────────────
function openConversation(conv) {
  if (isAgentMode.value) {
    router.push({ name: 'chat-dm', params: { conversationId: conv.conversation_id } })
  } else {
    router.push({
      name: 'chat-group',
      params: { roomId: roomId.value, conversationId: conv.conversation_id },
    })
  }
}

async function createConversation() {
  if (creating.value) return
  creating.value = true
  createError.value = ''
  try {
    const response = isAgentMode.value
      ? await imApi.createAgentConversation(agentId.value, { title: '' })
      : await imApi.createRoomConversation(roomId.value, { title: '' })
    const newId = response?.item?.conversation_id
    if (!newId) {
      createError.value = '新建对话失败：未返回会话标识'
      return
    }
    if (isAgentMode.value) {
      router.push({ name: 'chat-dm', params: { conversationId: newId } })
    } else {
      router.push({ name: 'chat-group', params: { roomId: roomId.value, conversationId: newId } })
    }
  } catch (error) {
    createError.value = error?.message || '新建对话失败，请重试'
  } finally {
    creating.value = false
  }
}

// ── 生命周期 ───────────────────────────────────────────────
onMounted(async () => {
  loading.value = true
  try {
    if (!chat.agents.length) await chat.bootstrap()
    chat.fetchActiveRuns().catch(() => {})
    await loadConversations()
  } catch {
    conversations.value = []
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="picker">
    <!-- 吸顶返回条 -->
    <div class="glass-bar bar">
      <button class="back-btn pressable" aria-label="返回" @click="router.back()">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
          <path d="M15 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <span class="bar-title">{{ entityTitle }}</span>
      <span class="bar-spacer" />
    </div>

    <div class="body">
      <!-- 实体名片 -->
      <div class="entity">
        <div class="avatar entity-avatar" :class="[`hue-${hueIndex(entityId)}`, { 'entity-avatar--group': !isAgentMode }]">
          <img v-if="entityAvatarUrl" :src="entityAvatarUrl" alt="" />
          <template v-else-if="isAgentMode">{{ firstChar(entityTitle) }}</template>
          <svg v-else viewBox="0 0 24 24" width="32" height="32" aria-hidden="true">
            <circle cx="9" cy="9" r="3.2" fill="#fff" opacity="0.95" />
            <circle cx="16" cy="10" r="2.6" fill="#fff" opacity="0.75" />
            <path d="M3.5 18.5c0-3 2.6-4.6 5.5-4.6s5.5 1.6 5.5 4.6" fill="#fff" opacity="0.95" />
            <path d="M14.5 18.5c0-2.2 1.4-3.6 3.4-3.6 2 0 3.1 1.3 3.1 3.2" fill="#fff" opacity="0.7" />
          </svg>
        </div>
        <div class="entity-info">
          <div class="entity-name-row">
            <span class="entity-name">{{ entityTitle }}</span>
            <span v-if="isAgentMode" class="chip" :class="agentTypeMeta.cls">{{ agentTypeMeta.label }}</span>
          </div>
          <div v-if="entityRunning" class="entity-running">
            <span class="dot dot--running" />智能体正在运行…
          </div>
          <div v-else class="entity-sub">{{ entitySubtitle }}</div>
        </div>
      </div>

      <!-- 加载骨架屏 -->
      <template v-if="loading">
        <div class="section-label">对话</div>
        <div class="conv-list">
          <div v-for="n in 3" :key="n" class="card-line conv-row skeleton-row">
            <div class="sk-lines">
              <div class="sk sk-line sk-line-1" />
              <div class="sk sk-line sk-line-2" />
            </div>
          </div>
        </div>
      </template>

      <!-- 空态 -->
      <div v-else-if="!conversations.length" class="empty">
        <div class="empty-icon">💬</div>
        <div>还没有对话</div>
        <div class="empty-hint">点下方按钮开始第一条</div>
      </div>

      <!-- 会话列表 -->
      <template v-else>
        <div class="section-label">
          对话 <span class="count-pill">{{ conversations.length }}</span>
        </div>
        <div class="conv-list">
          <button
            v-for="(conv, index) in conversations"
            :key="conv.conversation_id"
            class="card-line conv-row pressable rise-in"
            :style="{ animationDelay: `${index * 0.03}s` }"
            @click="openConversation(conv)"
          >
            <div class="conv-head">
              <span class="conv-title">{{ conv.title?.trim() || '未命名对话' }}</span>
              <span class="conv-time">{{ formatTime(conv.last_message?.created_at || conv.updated_at) }}</span>
            </div>
            <div class="conv-foot">
              <span v-if="chat.runningConversationIds.has(conv.conversation_id)" class="conv-sub running">
                <span class="dot dot--running" />智能体正在运行…
              </span>
              <span v-else class="conv-sub">{{ summarize(conv.last_message) || '暂无消息' }}</span>
              <span v-if="chat.unreadForConversation(conv.conversation_id) > 0" class="badge">
                {{ chat.unreadForConversation(conv.conversation_id) > 99 ? '99+' : chat.unreadForConversation(conv.conversation_id) }}
              </span>
            </div>
          </button>
        </div>
      </template>
    </div>

    <!-- 底部新建按钮 -->
    <div class="footer">
      <div v-if="createError" class="error-bar">{{ createError }}</div>
      <button class="btn-primary" :disabled="creating" @click="createConversation">
        <span v-if="creating">新建中…</span>
        <span v-else>＋ 新建对话</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.picker {
  min-height: 100%;
  padding-bottom: calc(var(--safe-bottom) + 90px);
}

/* 吸顶条 */
.bar {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 52px;
  padding: 0 8px;
  padding-top: var(--safe-top);
  height: calc(52px + var(--safe-top));
}

.back-btn {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: var(--r-pill);
  color: var(--ink);
}

.bar-title {
  flex: 1;
  min-width: 0;
  font-size: 17px;
  font-weight: 700;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-spacer {
  flex: none;
  width: 38px;
}

.body {
  padding: 0 var(--page-pad);
}

/* 实体名片 */
.entity {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 4px 8px;
}

.entity-avatar {
  width: 64px;
  height: 64px;
  font-size: 26px;
  flex: none;
}

.entity-avatar--group {
  border-radius: 22px;
}

.entity-info {
  flex: 1;
  min-width: 0;
}

.entity-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.entity-name {
  min-width: 0;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-sub {
  margin-top: 4px;
  font-size: 14px;
  color: var(--muted);
  line-height: 1.4;
}

.entity-running {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 5px;
  font-size: 14px;
  font-weight: 600;
  color: var(--green);
}

.chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 8px;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: 700;
}

.chip-exec {
  background: var(--accent-soft);
  color: var(--accent);
}

.chip-plan {
  background: rgba(139, 92, 246, 0.14);
  color: #7c3aed;
}

/* 会话列表 */
.conv-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.conv-row {
  display: block;
  width: 100%;
  padding: 13px 15px;
  text-align: left;
}

.conv-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.conv-title {
  flex: 1;
  min-width: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  flex: none;
  font-size: 12px;
  color: var(--muted-2);
}

.conv-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.conv-sub {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-sub.running {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--green);
  font-weight: 600;
}

.conv-foot .badge {
  flex: none;
}

/* 空态补充 */
.empty-hint {
  font-size: 13px;
  color: var(--muted-2);
}

/* 底部 */
.footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 12px var(--page-pad) calc(var(--safe-bottom) + 14px);
  background: linear-gradient(180deg, rgba(244, 246, 251, 0), var(--bg) 38%);
}

.error-bar {
  margin-bottom: 10px;
  padding: 10px 14px;
  border-radius: var(--r-md);
  background: var(--red-soft);
  color: var(--red);
  font-size: 13.5px;
  font-weight: 600;
  text-align: center;
}

/* Skeleton */
.skeleton-row {
  pointer-events: none;
}

.sk {
  background: linear-gradient(
    100deg,
    var(--bg-deep) 30%,
    rgba(255, 255, 255, 0.6) 50%,
    var(--bg-deep) 70%
  );
  background-size: 200% 100%;
  animation: shimmer 1.3s ease-in-out infinite;
  border-radius: 8px;
}

.sk-lines {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.sk-line {
  height: 13px;
}

.sk-line-1 {
  width: 45%;
}

.sk-line-2 {
  width: 78%;
}

@keyframes shimmer {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}
</style>
