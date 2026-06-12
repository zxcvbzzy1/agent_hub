<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlayCircleOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  RobotOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import axios from 'axios'
import { isTauri } from '@/desktop'
import { procApi } from '@/desktop/processes'
import { API_BASE_URL } from '@/api/http'
import { useIMStore } from '@/stores/im'

const KINDS = [
  { kind: 'mongod', title: 'MongoDB', icon: DatabaseOutlined, desc: '存储服务（im_backend 依赖，必须先就绪）' },
  { kind: 'backend', title: 'im_backend', icon: CloudServerOutlined, desc: 'FastAPI + agent_flow 运行时（uvicorn）' },
]

const im = useIMStore()
const cancellingRuns = reactive({})
// 触发重渲染用的时钟：让「已运行 Xs」每秒走动
const nowTick = ref(Math.floor(Date.now() / 1000))
let tickTimer = null
let runsTimer = null

const RUN_STATUS_META = {
  pending: { text: '排队中', color: 'gold' },
  running: { text: '运行中', color: 'green' },
  finished: { text: '已完成', color: 'blue' },
  failed: { text: '失败', color: 'red' },
  cancelled: { text: '已中断', color: 'default' },
}

function runStatusMeta(status) {
  return RUN_STATUS_META[status] || { text: status || '未知', color: 'default' }
}

function agentLabel(agentId) {
  if (!agentId) return ''
  const agent = im.agents.find((item) => item.agent_id === agentId)
  return agent?.name || agentId
}

function runAgents(run) {
  const names = (run.agent_ids || []).filter(Boolean).map(agentLabel)
  return names.length ? names.join('、') : '—'
}

function runScopeLabel(run) {
  if (run.kind === 'dm_reply') return run.conversation_title ? `单聊 · ${run.conversation_title}` : '单聊回复'
  if (run.room_title) return `群聊 · ${run.room_title}`
  return run.room_id ? '群聊任务' : '编排任务'
}

function runElapsed(run) {
  const start = run.started_at || run.created_at
  if (!start) return ''
  const end = run.finished_at || nowTick.value
  const seconds = Math.max(0, Math.floor(end - start))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

async function cancelRun(run) {
  cancellingRuns[run.run_id] = true
  try {
    await im.cancelAnyRun(run.run_id)
    message.success('已发送中断')
  } catch (error) {
    message.error(error?.response?.data?.detail || '中断失败')
  } finally {
    cancellingRuns[run.run_id] = false
  }
}

const statuses = ref([])
const health = ref(null) // /health 响应：{ status, mongo: 'mongodb'|'memory' }
const logsByKind = reactive({ mongod: [], backend: [] })
const activeLogTab = ref('backend')
const busy = reactive({})
const startAllBusy = ref(false)
const settingsOpen = ref(false)
const settingsForm = reactive({
  repo_dir: '',
  python_path: '',
  mongod_path: '',
  mongo_dbpath: '',
  mongo_port: 27017,
  backend_port: 8010,
  auto_start: false,
  stop_on_exit: true,
})

let pollTimer = null
let unlistenLog = null
let unlistenExit = null
const logPane = ref(null)

const statusMap = computed(() => {
  const map = {}
  for (const s of statuses.value) map[s.kind] = s
  return map
})

function stateOf(kind) {
  const s = statusMap.value[kind]
  if (!s) return { text: '未知', color: 'default' }
  if (s.managed) return { text: `托管运行中 (pid ${s.pid})`, color: 'green' }
  if (s.port_open) return { text: '外部运行中（非桌面端启动）', color: 'blue' }
  return { text: '未运行', color: 'default' }
}

async function refreshStatus() {
  if (!isTauri) return
  try {
    statuses.value = await procApi.status()
  } catch (error) {
    // 状态轮询失败不打扰用户，页面上保持旧状态。
    console.warn('proc_status failed', error)
  }
  // 后端健康检查直接打 /health：能拿到 mongo=memory 时要醒目告警（静默内存降级陷阱）。
  try {
    const r = await axios.get(`${API_BASE_URL}/health`, { timeout: 2500 })
    health.value = r.data
  } catch {
    health.value = null
  }
}

async function loadLogs(kind) {
  if (!isTauri) return
  try {
    logsByKind[kind] = await procApi.logs(kind)
  } catch {
    logsByKind[kind] = []
  }
}

function appendLog(entry) {
  const list = logsByKind[entry.kind]
  if (!list) return
  list.push(entry)
  if (list.length > 800) list.splice(0, list.length - 800)
  scrollLogToBottom()
}

function scrollLogToBottom() {
  requestAnimationFrame(() => {
    const el = logPane.value
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) {
      el.scrollTop = el.scrollHeight
    }
  })
}

async function runAction(kind, action) {
  busy[kind] = true
  try {
    await procApi[action](kind)
    message.success(`${kind} ${action === 'stop' ? '已停止' : '操作成功'}`)
  } catch (error) {
    message.error(String(error))
  } finally {
    busy[kind] = false
    await refreshStatus()
  }
}

async function startAll() {
  startAllBusy.value = true
  try {
    const report = await procApi.startAll()
    message.success(report.join('；'))
  } catch (error) {
    message.error(String(error))
  } finally {
    startAllBusy.value = false
    await refreshStatus()
  }
}

async function openSettings() {
  try {
    Object.assign(settingsForm, await procApi.getSettings())
    settingsOpen.value = true
  } catch (error) {
    message.error(String(error))
  }
}

async function saveSettings() {
  try {
    await procApi.saveSettings({ ...settingsForm })
    settingsOpen.value = false
    message.success('设置已保存')
    await refreshStatus()
  } catch (error) {
    message.error(String(error))
  }
}

function formatTs(ts) {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

onMounted(async () => {
  // 智能体运行监控走 HTTP，浏览器/桌面都可用；本页打开时用更高频率刷新。
  im.fetchAgents().catch(() => {})
  im.fetchActiveRuns().catch(() => {})
  runsTimer = setInterval(() => im.fetchActiveRuns().catch(() => {}), 3000)
  tickTimer = setInterval(() => {
    nowTick.value = Math.floor(Date.now() / 1000)
  }, 1000)

  if (!isTauri) return
  await refreshStatus()
  await Promise.all([loadLogs('mongod'), loadLogs('backend')])
  unlistenLog = await procApi.onLog(appendLog)
  unlistenExit = await procApi.onExit(() => refreshStatus())
  pollTimer = setInterval(refreshStatus, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (runsTimer) clearInterval(runsTimer)
  if (tickTimer) clearInterval(tickTimer)
  if (unlistenLog) unlistenLog()
  if (unlistenExit) unlistenExit()
})
</script>

<template>
  <div class="processes-view">
    <!-- ── 智能体运行监控：纯 HTTP，桌面端/浏览器都可用 ── -->
    <div class="page-head">
      <div>
        <h2>智能体运行</h2>
        <p class="sub">全局视图：单聊回复与群聊编排任务都在这里，可直接中断。</p>
      </div>
      <a-tag v-if="im.activeRuns.length" color="green" class="running-count-tag">
        {{ im.activeRuns.length }} 个运行中
      </a-tag>
    </div>

    <div v-if="!im.activeRuns.length" class="runs-empty">
      <RobotOutlined />
      <span>当前没有正在运行的智能体。发起一条对话或派发群聊任务后，这里会实时出现。</span>
    </div>
    <div v-else class="run-cards">
      <a-card v-for="run in im.activeRuns" :key="run.run_id" class="run-card">
        <div class="run-card-head">
          <RobotOutlined class="run-icon" />
          <div class="run-title">
            <strong>{{ runAgents(run) }}</strong>
            <span>{{ runScopeLabel(run) }}<template v-if="run.mode"> · {{ run.mode }}</template></span>
          </div>
          <a-tag :color="runStatusMeta(run.status).color" style="margin: 0">
            {{ runStatusMeta(run.status).text }}
          </a-tag>
        </div>
        <p class="run-prompt" :title="run.prompt">{{ run.prompt || '（无任务描述）' }}</p>
        <div class="run-meta">
          <span class="run-elapsed">已运行 {{ runElapsed(run) }}</span>
          <a-popconfirm
            title="确定中断这个运行？正在执行的工具调用会被取消。"
            ok-text="中断"
            cancel-text="再想想"
            @confirm="cancelRun(run)"
          >
            <a-button size="small" danger :loading="cancellingRuns[run.run_id]">
              <template #icon><StopOutlined /></template>
              中断
            </a-button>
          </a-popconfirm>
        </div>
      </a-card>
    </div>

    <a-card v-if="im.recentRuns.length" class="recent-card" title="最近结束（只读）" size="small">
      <div class="recent-list">
        <div v-for="run in im.recentRuns" :key="`recent-${run.run_id}`" class="recent-row">
          <a-tag :color="runStatusMeta(run.status).color" class="recent-status">
            {{ runStatusMeta(run.status).text }}
          </a-tag>
          <span class="recent-agents">{{ runAgents(run) }}</span>
          <span class="recent-scope">{{ runScopeLabel(run) }}</span>
          <span class="recent-prompt" :title="run.prompt">{{ run.prompt }}</span>
          <span class="recent-elapsed">{{ runElapsed(run) }}</span>
        </div>
      </div>
    </a-card>

    <a-alert
      v-if="!isTauri"
      type="info"
      show-icon
      message="本地服务托管仅在桌面端可用"
      description="当前在浏览器里运行，下方 MongoDB / im_backend 进程托管不可用。请通过 AgentHub 桌面 App 打开。"
    />

    <template v-else>
      <div class="page-head">
        <div>
          <h2>本地服务进程</h2>
          <p class="sub">托管 MongoDB 与 im_backend：状态、日志与生命周期都在这里。</p>
        </div>
        <a-space>
          <a-button @click="openSettings">
            <template #icon><SettingOutlined /></template>
            设置
          </a-button>
          <a-button type="primary" :loading="startAllBusy" @click="startAll">
            <template #icon><ThunderboltOutlined /></template>
            一键启动全部
          </a-button>
        </a-space>
      </div>

      <a-alert
        v-if="health && health.mongo === 'memory'"
        type="error"
        show-icon
        class="memory-warning"
        message="后端正运行在内存存储模式（Mongo 未连上）！"
        description="im_backend 启动时 Mongo 没就绪，已静默降级为内存存储——数据重启即丢。请先确认 MongoDB 运行正常，然后重启 im_backend。"
      />

      <div class="proc-cards">
        <a-card v-for="item in KINDS" :key="item.kind" class="proc-card">
          <div class="proc-card-head">
            <component :is="item.icon" class="proc-icon" />
            <div class="proc-title">
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </div>
            <a-tag :color="stateOf(item.kind).color">{{ stateOf(item.kind).text }}</a-tag>
          </div>
          <div class="proc-meta">
            <span>端口 {{ statusMap[item.kind]?.port ?? '—' }}</span>
            <span>
              端口状态：
              <a-badge
                :status="statusMap[item.kind]?.port_open ? 'success' : 'default'"
                :text="statusMap[item.kind]?.port_open ? '可连通' : '未监听'"
              />
            </span>
            <span v-if="item.kind === 'backend' && health">
              存储：
              <a-tag :color="health.mongo === 'mongodb' ? 'green' : 'red'" style="margin: 0">
                {{ health.mongo === 'mongodb' ? 'MongoDB' : '内存(危险)' }}
              </a-tag>
            </span>
          </div>
          <div class="proc-actions">
            <a-button
              size="small"
              type="primary"
              ghost
              :loading="busy[item.kind]"
              :disabled="statusMap[item.kind]?.managed || statusMap[item.kind]?.port_open"
              @click="runAction(item.kind, 'start')"
            >
              <template #icon><PlayCircleOutlined /></template>
              启动
            </a-button>
            <a-button
              size="small"
              danger
              :loading="busy[item.kind]"
              :disabled="!statusMap[item.kind]?.managed"
              @click="runAction(item.kind, 'stop')"
            >
              <template #icon><PoweroffOutlined /></template>
              停止
            </a-button>
            <a-button
              size="small"
              :loading="busy[item.kind]"
              :disabled="!statusMap[item.kind]?.managed"
              @click="runAction(item.kind, 'restart')"
            >
              <template #icon><ReloadOutlined /></template>
              重启
            </a-button>
          </div>
        </a-card>
      </div>

      <a-card class="log-card" :body-style="{ padding: '0' }">
        <a-tabs v-model:activeKey="activeLogTab" class="log-tabs">
          <a-tab-pane key="backend" tab="im_backend 日志" />
          <a-tab-pane key="mongod" tab="MongoDB 日志" />
        </a-tabs>
        <div ref="logPane" class="log-pane">
          <div v-if="!logsByKind[activeLogTab].length" class="log-empty">
            暂无日志——只有由桌面端托管启动的进程才会在这里输出。
          </div>
          <div
            v-for="(entry, index) in logsByKind[activeLogTab]"
            :key="index"
            class="log-line"
            :class="`log-${entry.stream}`"
          >
            <span class="log-ts">{{ formatTs(entry.ts) }}</span>
            <span class="log-text">{{ entry.line }}</span>
          </div>
        </div>
      </a-card>

      <a-drawer v-model:open="settingsOpen" title="进程托管设置" width="520">
        <a-form layout="vertical">
          <a-form-item label="仓库目录（PYTHONPATH / 工作目录）">
            <a-input v-model:value="settingsForm.repo_dir" />
          </a-form-item>
          <a-form-item label="Python 路径（MY_env）">
            <a-input v-model:value="settingsForm.python_path" />
          </a-form-item>
          <a-form-item label="mongod 路径">
            <a-input v-model:value="settingsForm.mongod_path" />
          </a-form-item>
          <a-form-item label="Mongo 数据目录 (--dbpath)">
            <a-input v-model:value="settingsForm.mongo_dbpath" />
          </a-form-item>
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="Mongo 端口">
                <a-input-number v-model:value="settingsForm.mongo_port" :min="1" :max="65535" style="width: 100%" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="后端端口">
                <a-input-number v-model:value="settingsForm.backend_port" :min="1" :max="65535" style="width: 100%" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item>
            <a-checkbox v-model:checked="settingsForm.auto_start">App 启动时自动拉起全部服务</a-checkbox>
          </a-form-item>
          <a-form-item>
            <a-checkbox v-model:checked="settingsForm.stop_on_exit">App 退出时停止托管进程（外部启动的不受影响）</a-checkbox>
          </a-form-item>
        </a-form>
        <template #footer>
          <a-space>
            <a-button @click="settingsOpen = false">取消</a-button>
            <a-button type="primary" @click="saveSettings">保存</a-button>
          </a-space>
        </template>
      </a-drawer>
    </template>
  </div>
</template>

<style scoped>
.processes-view {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 20px 48px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.page-head h2 {
  margin: 0;
  font-size: 20px;
}

.page-head .sub {
  margin: 4px 0 0;
  color: var(--muted, #5f6f8b);
  font-size: 13px;
}

.memory-warning {
  border-radius: 12px;
}

/* ── 智能体运行区 ── */
.running-count-tag {
  font-weight: 700;
}

.runs-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 18px;
  border: 1px dashed rgba(95, 111, 139, 0.32);
  border-radius: 14px;
  color: var(--muted, #5f6f8b);
  font-size: 13px;
}

.run-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.run-card {
  border-radius: 14px;
}

.run-card-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.run-icon {
  font-size: 24px;
  color: var(--accent, #3578ff);
}

.run-title {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.run-title strong {
  font-size: 14.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-title span {
  color: var(--muted, #5f6f8b);
  font-size: 12px;
}

.run-prompt {
  margin: 12px 0;
  color: var(--text, #1f2a44);
  font-size: 12.5px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.run-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.run-elapsed {
  color: var(--muted, #5f6f8b);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.recent-card {
  border-radius: 14px;
}

.recent-list {
  display: flex;
  flex-direction: column;
}

.recent-row {
  display: grid;
  grid-template-columns: 76px 150px 170px 1fr 70px;
  align-items: center;
  gap: 10px;
  padding: 7px 2px;
  border-bottom: 1px solid rgba(95, 111, 139, 0.10);
  font-size: 12.5px;
}

.recent-row:last-child {
  border-bottom: none;
}

.recent-status {
  margin: 0;
  text-align: center;
}

.recent-agents,
.recent-scope,
.recent-prompt {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-agents {
  font-weight: 650;
}

.recent-scope,
.recent-prompt {
  color: var(--muted, #5f6f8b);
}

.recent-elapsed {
  color: var(--muted, #5f6f8b);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.proc-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.proc-card {
  border-radius: 14px;
}

.proc-card-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.proc-icon {
  font-size: 26px;
  color: var(--accent, #3578ff);
}

.proc-title {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.proc-title strong {
  font-size: 15px;
}

.proc-title span {
  color: var(--muted, #5f6f8b);
  font-size: 12px;
}

.proc-meta {
  display: flex;
  gap: 18px;
  margin: 14px 0 12px;
  color: var(--muted, #5f6f8b);
  font-size: 12.5px;
  flex-wrap: wrap;
  align-items: center;
}

.proc-actions {
  display: flex;
  gap: 8px;
}

.log-card {
  border-radius: 14px;
  overflow: hidden;
}

.log-tabs :deep(.ant-tabs-nav) {
  margin: 0;
  padding: 0 16px;
}

.log-pane {
  height: 340px;
  overflow: auto;
  background: #0d1422;
  padding: 12px 14px;
  font-family: 'SF Mono', ui-monospace, Menlo, monospace;
  font-size: 12px;
  line-height: 1.65;
}

.log-empty {
  color: rgba(255, 255, 255, 0.45);
  padding: 18px 4px;
}

.log-line {
  display: flex;
  gap: 10px;
  color: rgba(235, 242, 255, 0.88);
  word-break: break-all;
}

.log-line.log-stderr .log-text {
  color: #ff9a8a;
}

.log-line.log-system .log-text {
  color: #7fd4ff;
  font-weight: 700;
}

.log-ts {
  flex: none;
  color: rgba(255, 255, 255, 0.38);
}

@media (max-width: 860px) {
  .proc-cards,
  .run-cards {
    grid-template-columns: 1fr;
  }

  .recent-row {
    grid-template-columns: 76px 1fr 70px;
  }

  .recent-scope,
  .recent-prompt {
    display: none;
  }
}
</style>
