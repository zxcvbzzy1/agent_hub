<script setup>
// 审批中心：聚合全部活跃 run 的待人工确认（危险命令审批）+ 运行中的任务（可中断）。
// 数据链路：GET /runs/active → 逐 run GET /runs/{id}/confirmations（个人规模，量很小）。
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
const loading = ref(true)
const busy = reactive({})
const expanded = reactive({})
const errorText = ref('')
let pollTimer = null

async function refresh() {
  try {
    await chat.fetchPendingApprovals()
    errorText.value = ''
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '加载失败，请检查服务器连接'
  } finally {
    loading.value = false
  }
}

async function resolve(item, approved) {
  const key = item.confirmation_id
  busy[key] = true
  try {
    await chat.resolveConfirmation(item.run_id || item.run?.run_id, key, approved)
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '审批提交失败'
  } finally {
    busy[key] = false
  }
}

async function interruptRun(run) {
  busy[run.run_id] = true
  try {
    await chat.cancelAnyRun(run.run_id)
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '中断失败'
  } finally {
    busy[run.run_id] = false
  }
}

function argsText(item) {
  const args = item.arguments ?? item.args ?? {}
  if (typeof args === 'string') return args
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args)
  }
}

function runAgents(run) {
  const names = (run.agent_ids || [])
    .filter(Boolean)
    .map((agentId) => chat.agentById[agentId]?.name || agentId)
  return names.length ? names.join('、') : '智能体'
}

function runScope(run) {
  if (run.kind === 'dm_reply') return run.conversation_title ? `单聊 · ${run.conversation_title}` : '单聊回复'
  return run.room_title ? `群聊 · ${run.room_title}` : '编排任务'
}

// 纯展示：根据 agentId 字符串哈希到 hue-0..hue-5
function hueClass(agentId) {
  if (!agentId) return 'hue-0'
  let h = 0
  for (let i = 0; i < agentId.length; i++) h = (h * 31 + agentId.charCodeAt(i)) >>> 0
  return `hue-${h % 6}`
}

// 纯展示：取 agentId 对应 agent name 首字母（或 agentId 首字母）
function runAvatarLetter(run) {
  const id = (run.agent_ids || [])[0]
  if (!id) return '?'
  const name = (chat.agentById && chat.agentById[id]?.name) || id
  return name.slice(0, 1).toUpperCase()
}

onMounted(async () => {
  if (!chat.agents.length) chat.bootstrap().catch(() => {})
  await refresh()
  pollTimer = setInterval(refresh, 8000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">审批</h1>

    <div v-if="errorText" class="error-bar" @click="errorText = ''">{{ errorText }}</div>

    <!-- 待审批 -->
    <section>
      <h2 class="sec-title section-label">
        待审批
        <span v-if="chat.pendingApprovals.length" class="badge count-pill">{{ chat.pendingApprovals.length }}</span>
      </h2>

      <div v-if="loading" class="card skeleton-card"></div>
      <div v-else-if="!chat.pendingApprovals.length" class="empty empty-card empty-dashed">
        <span class="empty-icon empty-icon-lg">✅</span>
        <span>没有等待你审批的操作</span>
      </div>

      <div v-else class="approval-list">
        <div v-for="item in chat.pendingApprovals" :key="item.confirmation_id" class="card approval-card rise-in">
          <div class="approval-head">
            <span class="approval-flag">⚠️</span>
            <div class="approval-title">
              <strong>{{ item.tool_name || '工具调用' }}</strong>
              <span>{{ item.run ? runScope(item.run) : '' }}</span>
            </div>
          </div>

          <p v-if="item.run?.prompt" class="approval-prompt">任务：{{ item.run.prompt }}</p>

          <button class="args-toggle" @click="expanded[item.confirmation_id] = !expanded[item.confirmation_id]">
            {{ expanded[item.confirmation_id] ? '收起参数' : '查看参数' }}
          </button>
          <pre v-if="expanded[item.confirmation_id]" class="approval-args">{{ argsText(item) }}</pre>

          <div class="approval-actions">
            <button class="btn-danger act-btn" :disabled="busy[item.confirmation_id]" @click="resolve(item, false)">
              拒绝
            </button>
            <button class="btn-ghost act-btn act-allow" :disabled="busy[item.confirmation_id]" @click="resolve(item, true)">
              允许执行
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- 运行中的任务 -->
    <section class="runs-section">
      <h2 class="sec-title section-label">
        运行中
        <span v-if="chat.activeRuns.length" class="run-count count-pill">{{ chat.activeRuns.length }}</span>
      </h2>

      <div v-if="!chat.activeRuns.length" class="empty empty-card empty-dashed">
        <span class="empty-icon empty-icon-lg">🌙</span>
        <span>当前没有正在运行的智能体</span>
      </div>

      <div v-else class="card run-list">
        <div v-for="run in chat.activeRuns" :key="run.run_id" class="run-row">
          <div :class="['avatar', 'run-avatar', hueClass((run.agent_ids || [])[0])]">
            {{ runAvatarLetter(run) }}
          </div>
          <div class="run-info">
            <strong>{{ runAgents(run) }}</strong>
            <span>{{ runScope(run) }}<template v-if="run.prompt"> · {{ run.prompt.slice(0, 40) }}</template></span>
          </div>
          <button class="run-stop" :disabled="busy[run.run_id]" @click="interruptRun(run)">
            {{ busy[run.run_id] ? '…' : '中断' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* section 标题：复用 theme.css .section-label 风格，保留 badge/count 逻辑 */
.sec-title {
  margin: 4px 2px 10px;
}

/* 运行中 count badge：绿色 */
.run-count {
  background: var(--green-soft) !important;
  color: var(--green) !important;
}

.error-bar {
  margin-bottom: 12px;
  padding: 9px 13px;
  border-radius: var(--r-sm);
  background: var(--red-soft);
  color: var(--red);
  font-size: 13px;
}

/* 空态：虚线边框 */
.empty-dashed {
  border: 1.5px dashed rgba(15, 23, 42, 0.12);
  border-radius: var(--r-lg);
  background: var(--surface);
  padding: 40px 20px;
}

/* 空态图标放大 */
.empty-icon-lg {
  font-size: 52px !important;
  opacity: 0.6 !important;
}

.skeleton-card {
  height: 120px;
  background: linear-gradient(100deg, var(--surface) 40%, var(--bg-deep) 50%, var(--surface) 60%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}

@keyframes shimmer {
  to {
    background-position: -200% 0;
  }
}

.approval-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* approval-card：左侧 3px 琥珀色竖条（用伪元素，不破坏 padding） */
.approval-card {
  padding: 14px 16px 14px 20px;
  border: 1.5px solid rgba(217, 119, 6, 0.22);
  position: relative;
  overflow: hidden;
}

.approval-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--amber);
  border-radius: 3px 0 0 3px;
}

.approval-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.approval-flag {
  font-size: 20px;
}

.approval-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.approval-title strong {
  font-size: 15px;
}

.approval-title span {
  font-size: 12px;
  color: var(--muted);
}

.approval-prompt {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.args-toggle {
  margin-top: 8px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--accent);
}

.approval-args {
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: #0d1422;
  color: #e2ecff;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 11.5px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 220px;
  overflow-y: auto;
}

.approval-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.act-btn {
  flex: 1;
  height: 40px;
}

.act-allow {
  background: var(--green-soft);
  color: var(--green);
}

.runs-section {
  margin-top: 22px;
}

.run-list {
  padding: 4px 0;
}

.run-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px 16px;
}

.run-row + .run-row {
  border-top: 0.5px solid var(--line);
}

/* hue 渐变小头像 */
.run-avatar {
  width: 34px;
  height: 34px;
  font-size: 14px;
  flex: none;
}

.run-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.run-info strong {
  font-size: 14px;
}

.run-info span {
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-stop {
  flex: none;
  padding: 6px 14px;
  border-radius: var(--r-pill);
  background: var(--red-soft);
  color: var(--red);
  font-size: 12.5px;
  font-weight: 800;
}
</style>
