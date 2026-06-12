<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'

const router = useRouter()
const chat = useChatStore()

const loading = ref(true)
const query = ref('')

let pollHandle = null

// ── 工具 ───────────────────────────────────────────────────
function firstChar(name) {
  const trimmed = (name || '').trim()
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : '·'
}

// 稳定哈希 → hue-N 渐变索引
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

function agentDesc(agent) {
  const raw = agent?.description || agent?.metadata?.description || ''
  return clip(raw, 36) || '随时可以开始对话'
}

function agentTypeMeta(agent) {
  return agent?.agent_type === 'planner'
    ? { label: '规划', cls: 'chip-plan' }
    : { label: '执行', cls: 'chip-exec' }
}

function roomMembers(room) {
  const ids = room?.member_agent_ids || []
  const names = ids
    .map((id) => chat.agentById[id]?.name)
    .filter(Boolean)
    .slice(0, 2)
  let line = `${ids.length} 位成员`
  if (names.length) line += ` · ${names.join('、')}`
  return line
}

// ── 过滤分组 ───────────────────────────────────────────────
const filteredAgents = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = chat.executorAgents
  if (!q) return list
  return list.filter((a) => {
    const desc = a.description || a.metadata?.description || ''
    return (a.name || '').toLowerCase().includes(q) || desc.toLowerCase().includes(q)
  })
})

const filteredRooms = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = chat.rooms
  if (!q) return list
  return list.filter((r) => {
    return (r.title || '').toLowerCase().includes(q) || roomMembers(r).toLowerCase().includes(q)
  })
})

const hasNothing = computed(() => !filteredAgents.value.length && !filteredRooms.value.length)

// ── 交互 ───────────────────────────────────────────────────
function openAgent(agent) {
  router.push({ name: 'agent-conversations', params: { agentId: agent.agent_id } })
}
function openRoom(room) {
  router.push({ name: 'group-conversations', params: { roomId: room.room_id } })
}

// ── 生命周期 ───────────────────────────────────────────────
onMounted(async () => {
  loading.value = true
  try {
    await chat.bootstrap()
    await chat.fetchActiveRuns().catch(() => {})
  } finally {
    loading.value = false
  }

  pollHandle = setInterval(() => {
    Promise.all([chat.fetchActivity().catch(() => {}), chat.fetchActiveRuns().catch(() => {})])
  }, 10000)
})

onUnmounted(() => {
  if (pollHandle) {
    clearInterval(pollHandle)
    pollHandle = null
  }
})
</script>

<template>
  <div class="page home">
    <!-- 标题行 + 整体运行状态 chip -->
    <div class="title-row">
      <h1 class="page-title">AgentHub</h1>
      <div v-if="chat.activeRuns.length > 0" class="run-chip">
        <span class="dot dot--running" />
        {{ chat.activeRuns.length }} 个运行中
      </div>
    </div>

    <!-- 搜索 -->
    <div class="search">
      <svg class="search-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2" />
        <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
      <input v-model="query" type="search" placeholder="搜索智能体或群" />
    </div>

    <!-- 加载骨架屏 -->
    <template v-if="loading">
      <div class="section-label">智能体</div>
      <div class="sk-list">
        <div v-for="n in 3" :key="`a${n}`" class="card-line row skeleton-row">
          <div class="sk sk-avatar" />
          <div class="sk-lines">
            <div class="sk sk-line sk-line-1" />
            <div class="sk sk-line sk-line-2" />
          </div>
        </div>
      </div>
    </template>

    <!-- 全空引导态 -->
    <div v-else-if="hasNothing && !query.trim()" class="empty">
      <div class="empty-icon">🤖</div>
      <div>还没有任何智能体</div>
      <div class="empty-hint">请先在桌面端创建智能体或群</div>
    </div>
    <div v-else-if="hasNothing" class="empty">
      <div class="empty-icon">🔍</div>
      <div>没有匹配的结果</div>
    </div>

    <!-- 内容 -->
    <template v-else>
      <!-- 分组一：智能体 -->
      <template v-if="filteredAgents.length">
        <div class="section-label">
          智能体 <span class="count-pill">{{ filteredAgents.length }}</span>
        </div>
        <div class="group-list">
          <button
            v-for="(agent, index) in filteredAgents"
            :key="agent.agent_id"
            class="card-line row pressable rise-in"
            :style="{ animationDelay: `${index * 0.03}s` }"
            @click="openAgent(agent)"
          >
            <div class="avatar-wrap">
              <div class="avatar" :class="`hue-${hueIndex(agent.agent_id)}`">
                <img v-if="agent.metadata?.avatar_url" :src="agent.metadata.avatar_url" alt="" />
                <template v-else>{{ firstChar(agent.name) }}</template>
              </div>
              <span v-if="chat.runningAgentIds.has(agent.agent_id)" class="dot dot--running run-overlay" />
            </div>

            <div class="row-body">
              <div class="row-head">
                <span class="row-title">{{ agent.name || '智能体' }}</span>
                <span class="chip" :class="agentTypeMeta(agent).cls">{{ agentTypeMeta(agent).label }}</span>
              </div>
              <div class="row-sub">{{ agentDesc(agent) }}</div>
            </div>

            <div class="row-tail">
              <span v-if="chat.unreadForAgent(agent.agent_id) > 0" class="badge">
                {{ chat.unreadForAgent(agent.agent_id) > 99 ? '99+' : chat.unreadForAgent(agent.agent_id) }}
              </span>
              <svg class="chevron" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>
          </button>
        </div>
      </template>

      <!-- 分组二：群聊 -->
      <template v-if="filteredRooms.length">
        <div class="section-label">
          群聊 <span class="count-pill">{{ filteredRooms.length }}</span>
        </div>
        <div class="group-list">
          <button
            v-for="(room, index) in filteredRooms"
            :key="room.room_id"
            class="card-line row pressable rise-in"
            :style="{ animationDelay: `${(filteredAgents.length + index) * 0.03}s` }"
            @click="openRoom(room)"
          >
            <div class="avatar-wrap">
              <div class="avatar avatar-group" :class="`hue-${hueIndex(room.room_id)}`">
                <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
                  <circle cx="9" cy="9" r="3.2" fill="#fff" opacity="0.95" />
                  <circle cx="16" cy="10" r="2.6" fill="#fff" opacity="0.75" />
                  <path d="M3.5 18.5c0-3 2.6-4.6 5.5-4.6s5.5 1.6 5.5 4.6" fill="#fff" opacity="0.95" />
                  <path d="M14.5 18.5c0-2.2 1.4-3.6 3.4-3.6 2 0 3.1 1.3 3.1 3.2" fill="#fff" opacity="0.7" />
                </svg>
              </div>
              <span v-if="chat.runningRoomIds.has(room.room_id)" class="dot dot--running run-overlay" />
            </div>

            <div class="row-body">
              <div class="row-head">
                <span class="row-title">{{ room.title || '群聊' }}</span>
                <span class="chip chip-group">群</span>
              </div>
              <div class="row-sub">{{ roomMembers(room) }}</div>
            </div>

            <div class="row-tail">
              <span v-if="chat.unreadForRoom(room.room_id) > 0" class="badge">
                {{ chat.unreadForRoom(room.room_id) > 99 ? '99+' : chat.unreadForRoom(room.room_id) }}
              </span>
              <svg class="chevron" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>
          </button>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.title-row .page-title {
  margin-bottom: 6px;
}

.run-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  background: var(--green-soft);
  color: var(--green);
  font-size: 12.5px;
  font-weight: 700;
  white-space: nowrap;
}

/* 搜索 */
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  padding: 0 14px;
  margin: 8px 2px 4px;
  border-radius: var(--r-pill);
  background: var(--bg-deep);
}

.search-icon {
  flex: none;
  color: var(--muted-2);
}

.search input {
  flex: 1;
  height: 100%;
  font-size: 15px;
}

.search input::placeholder {
  color: var(--muted-2);
}

/* 列表 */
.group-list,
.sk-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row {
  display: flex;
  align-items: center;
  gap: 13px;
  width: 100%;
  padding: 12px 14px;
  text-align: left;
}

/* 头像 */
.avatar-wrap {
  position: relative;
  flex: none;
}

.avatar-wrap .avatar {
  width: 46px;
  height: 46px;
  font-size: 18px;
}

.avatar-group {
  border-radius: 18px;
}

.run-overlay {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 13px;
  height: 13px;
  border: 2px solid var(--surface);
  box-sizing: border-box;
}

/* 行主体 */
.row-body {
  flex: 1;
  min-width: 0;
}

.row-head {
  display: flex;
  align-items: center;
  gap: 7px;
}

.row-title {
  min-width: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 17px;
  padding: 0 7px;
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

.chip-group {
  background: var(--green-soft);
  color: var(--green);
}

.row-sub {
  margin-top: 3px;
  font-size: 13.5px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-tail {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.chevron {
  color: var(--muted-2);
}

/* 空态补充 */
.empty-hint {
  font-size: 13px;
  color: var(--muted-2);
}

/* Skeleton */
.skeleton-row {
  pointer-events: none;
  min-height: 70px;
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

.sk-avatar {
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: 14px;
}

.sk-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.sk-line {
  height: 13px;
}

.sk-line-1 {
  width: 40%;
}

.sk-line-2 {
  width: 70%;
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
