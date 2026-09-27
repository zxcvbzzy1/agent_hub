<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Grid, message } from 'ant-design-vue'
import { DatabaseOutlined, SearchOutlined, ReloadOutlined, ExperimentOutlined, SettingOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { listMemoryBlocks, getMemoryBlock, getMemorySource, getMemoryScopes, getMemorySettings, saveMemorySettings, testMemoryRecall } from '@/api/memory'
import { renderMarkdown } from '@/utils/markdown'
import MemoryProcessingPanel from '@/components/MemoryProcessingPanel.vue'

const tab = ref('browse')
const screens = Grid.useBreakpoint()
const detailColumns = computed(() => screens.value.sm ? 2 : 1)
const statusNames = { active: '有效', expired: '已过期', deleted: '已删除', merged: '已合并', superseded: '已有新版本', unavailable: '来源未就绪', all: '全部状态' }
const kindNames = { qa: '问答', think: '历史思考', derived: '派生记忆', extracted: '提取记忆' }
const categoryNames = { user_preference: '用户偏好', project_state: '项目状态', user_fact: '稳定用户事实', decision: '用户／系统决策', reusable_conclusion: '可复用实验结论' }
const reasonNames = { selected: '已入选', limit: '超过块数限制', token_budget: '超出 token 预算' }
const statusOptions = Object.entries(statusNames).map(([value, label]) => ({ value, label }))
const formatDate = (value) => value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'
const score = (value) => Number(value || 0).toFixed(4)
const statusColor = (value) => ({ active: 'green', expired: 'orange', deleted: 'red', unavailable: 'orange' }[value] || 'default')

const filters = reactive({ q: '', status: 'active', room_id: undefined, conversation_id: undefined })
const page = ref(1)
const pageSize = ref(20)
const items = ref([])
const total = ref(0)
const loading = ref(false)
const listError = ref(false)
const scopesError = ref(false)
const scopes = ref({ rooms: [], conversations: [] })
const conversationOptions = computed(() => scopes.value.conversations.filter((c) => !filters.room_id || c.room_id === filters.room_id))
let listRequest = 0

async function loadList(reset = false) {
  if (reset) page.value = 1
  const request = ++listRequest
  loading.value = true
  listError.value = false
  try {
    const response = await listMemoryBlocks({ ...filters, page: page.value, page_size: pageSize.value })
    if (request !== listRequest) return
    items.value = response.items
    total.value = response.total
  } catch {
    if (request === listRequest) { listError.value = true; items.value = []; total.value = 0 }
  } finally {
    if (request === listRequest) loading.value = false
  }
}
async function loadScopes() {
  scopesError.value = false
  try { scopes.value = await getMemoryScopes() } catch { scopesError.value = true }
}
function changeRoom() { filters.conversation_id = undefined; loadList(true) }
function changePage(next, size) { page.value = size === pageSize.value ? next : 1; pageSize.value = size; loadList() }

const drawer = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref(false)
const selectedId = ref('')
const source = ref(null)
const sourceLoading = ref(false)
const sourceError = ref(false)
const sourceRange = ref(null)
let sourceRequest = 0
let detailRequest = 0
async function openDetail(id) {
  const request = ++detailRequest
  selectedId.value = id
  drawer.value = true
  detail.value = null
  source.value = null
  sourceRange.value = null
  ++sourceRequest
  sourceError.value = false
  sourceLoading.value = false
  detailError.value = false
  detailLoading.value = true
  try {
    const response = await getMemoryBlock(id)
    if (request === detailRequest) detail.value = response
  } catch { if (request === detailRequest) detailError.value = true }
  finally { if (request === detailRequest) detailLoading.value = false }
}
async function loadSource(evidence = null) {
  const request = detailRequest
  const sourceSequence = ++sourceRequest
  const ref = evidence?.source_id ? evidence : (sourceRange.value || detail.value.item)
  sourceRange.value = ref
  source.value = null
  sourceLoading.value = true
  sourceError.value = false
  try {
    const response = await getMemorySource(ref.source_id)
    if (request === detailRequest && sourceSequence === sourceRequest) source.value = response.item
  } catch { if (request === detailRequest && sourceSequence === sourceRequest) sourceError.value = true }
  finally { if (request === detailRequest && sourceSequence === sourceRequest) sourceLoading.value = false }
}
function closeDrawer() { drawer.value = false; ++detailRequest }
function relationship(block) {
  if (detail.value.item.derived_from_block_ids?.includes(block.block_id)) return '派生自'
  if (detail.value.item.superseded_by_block_ids?.includes(block.block_id)) return '后续记忆'
  return `版本 ${block.version}`
}

const defaults = ref({ limit: 6, token_budget: 4000, k1: 1.5, b: 0.75 })
const draft = reactive({ ...defaults.value })
const saved = ref(null)
const settingsLoading = ref(false)
const settingsError = ref(false)
const saving = ref(false)
const configKeys = ['limit', 'token_budget', 'k1', 'b']
const sameConfig = (a, b) => a && b && configKeys.every((key) => a[key] === b[key])
const dirty = computed(() => saved.value && !sameConfig(draft, saved.value))
const validConfig = computed(() => Number.isInteger(draft.limit) && draft.limit >= 1 && draft.limit <= 50
  && Number.isInteger(draft.token_budget) && draft.token_budget >= 128 && draft.token_budget <= 32000
  && Number.isFinite(draft.k1) && draft.k1 > 0 && draft.k1 <= 5
  && Number.isFinite(draft.b) && draft.b >= 0 && draft.b <= 1)
async function loadSettings() {
  settingsLoading.value = true
  settingsError.value = false
  try {
    const response = await getMemorySettings()
    saved.value = response.item
    defaults.value = response.defaults
    Object.assign(draft, response.item)
  } catch { settingsError.value = true }
  finally { settingsLoading.value = false }
}
async function saveSettings() {
  if (!validConfig.value || saving.value) return
  saving.value = true
  try {
    const response = await saveMemorySettings({ ...draft })
    saved.value = response.item
    message.success('检索配置已保存，将用于下一次运行')
  } catch { /* The shared HTTP interceptor displays the error. */ }
  finally { saving.value = false }
}
const query = ref('')
const testing = ref(false)
const testError = ref(false)
const result = ref(null)
const testedQuery = ref('')
const staleResult = computed(() => result.value && (testedQuery.value !== query.value.trim() || !sameConfig(draft, result.value.config)))
const emptyMessage = computed(() => ({ no_memory: '还没有有效记忆。完成一次对话后，再来测试召回。', no_match: '没有与问题匹配的记忆，可以尝试换一种表达。', token_budget: '已找到匹配记忆，但候选块均超出当前 token 预算。' }[result.value?.empty_reason]))
async function testRecall() {
  if (!query.value.trim() || !validConfig.value || testing.value) return
  testing.value = true
  testError.value = false
  result.value = null
  const submittedQuery = query.value.trim()
  try {
    const response = await testMemoryRecall(submittedQuery, { ...draft })
    result.value = response.item
    testedQuery.value = submittedQuery
  } catch { testError.value = true }
  finally { testing.value = false }
}
onMounted(() => { loadList(); loadScopes(); loadSettings() })
</script>

<template>
  <main class="memory-workspace">
    <header class="memory-heading">
      <div class="heading-icon"><DatabaseOutlined /></div>
      <div><span class="eyebrow">MEMORY</span><h1>长期记忆</h1><p>查看积累的记忆，调整检索方式，验证召回效果。</p></div>
      <a-tag class="account-tag" color="blue">当前账号 · 跨房间检索</a-tag>
    </header>

    <a-tabs v-model:activeKey="tab" class="memory-tabs">
      <a-tab-pane key="browse">
        <template #tab><span><DatabaseOutlined /> 记忆查询</span></template>
        <section class="memory-panel">
          <form class="filter-grid" @submit.prevent="loadList(true)">
            <label class="search-field">关键词<a-input v-model:value="filters.q" allow-clear placeholder="搜索记忆正文或标签" :maxlength="1000"><template #prefix><SearchOutlined /></template></a-input></label>
            <label>状态<a-select v-model:value="filters.status" :options="statusOptions" @change="loadList(true)" /></label>
            <label>房间<a-select v-model:value="filters.room_id" :options="scopes.rooms" allow-clear show-search option-filter-prop="label" placeholder="全部房间" @change="changeRoom" /></label>
            <label>会话<a-select v-model:value="filters.conversation_id" :options="conversationOptions" allow-clear show-search option-filter-prop="label" placeholder="全部会话" @change="loadList(true)" /></label>
            <a-button type="primary" html-type="submit" :loading="loading">查询</a-button>
          </form>
          <a-alert v-if="scopesError" type="warning" message="房间和会话选项加载失败" show-icon class="notice"><template #action><a-button size="small" @click="loadScopes">重试</a-button></template></a-alert>
          <div class="list-heading"><span>共 <strong>{{ total }}</strong> 条记忆</span><a-button type="text" :loading="loading" @click="loadList()"><template #icon><ReloadOutlined /></template>刷新</a-button></div>
          <a-spin :spinning="loading">
            <a-result v-if="listError" status="warning" title="记忆加载失败" sub-title="请重试获取当前账号的记忆。"><template #extra><a-button @click="loadList()">重新加载</a-button></template></a-result>
            <a-empty v-else-if="!loading && !items.length" description="当前条件下没有记忆" class="empty-state" />
            <div v-else class="memory-grid">
              <button v-for="item in items" :key="item.block_id" class="memory-card" @click="openDetail(item.block_id)">
                <div class="card-top"><span class="kind-label"><FileTextOutlined /> {{ kindNames[item.section_kind] || item.section_kind }}</span><a-tag :color="statusColor(item.status)">{{ statusNames[item.status] || item.status }}</a-tag></div>
                <p class="card-summary">{{ item.summary }}</p>
                <div class="card-tags"><a-tag>{{ item.memory_type === 'unclassified' ? '未分类' : item.memory_type }}</a-tag><a-tag v-for="tag in item.tags" :key="tag" color="blue">{{ tag }}</a-tag></div>
                <div class="card-source">{{ item.room_name }} / {{ item.conversation_name }}</div>
                <div class="card-meta"><span>约 {{ item.token_count }} tokens</span><span>使用 {{ item.usage_count }} 次</span><span>v{{ item.version }}</span></div>
                <div class="card-date">更新于 {{ formatDate(item.updated_at) }}<span>查看详情 →</span></div>
              </button>
            </div>
          </a-spin>
          <a-pagination v-if="total" class="memory-pagination" :current="page" :page-size="pageSize" :total="total" show-size-changer :page-size-options="['20', '50', '100']" :responsive="true" @change="changePage" />
        </section>
      </a-tab-pane>

      <a-tab-pane key="retrieve">
        <template #tab><span><ExperimentOutlined /> 检索配置与测试</span></template>
        <div class="retrieval-layout">
          <section class="memory-panel config-panel">
            <div class="panel-title"><SettingOutlined /><h2>检索配置</h2><a-tag v-if="saved" :color="dirty ? 'orange' : 'green'">{{ dirty ? '未保存草稿' : '已保存' }}</a-tag></div>
            <p class="muted">保存后用于当前账号的下一次运行。测试始终使用当前表单参数。</p>
            <a-spin :spinning="settingsLoading">
              <a-alert v-if="settingsError" type="error" show-icon message="配置加载失败"><template #action><a-button size="small" @click="loadSettings">重试</a-button></template></a-alert>
              <fieldset :disabled="!saved || settingsLoading" class="config-fields">
                <label>最大召回块数<a-input-number v-model:value="draft.limit" aria-label="最大召回块数" :min="1" :max="50" :precision="0" /><small>最多 50 块，按相关度和预算选择。</small></label>
                <label>上下文 token 预算<a-input-number v-model:value="draft.token_budget" aria-label="上下文 token 预算" :min="128" :max="32000" :precision="0" :step="128" /><small>包含最终注入文本的格式开销，使用估算值。</small></label>
                <div class="bm25-heading">BM25 参数</div>
                <label>词频权重 k1<a-input-number v-model:value="draft.k1" aria-label="词频权重 k1" :min="0" :max="5" :step="0.1" /><small>大于 0，控制重复出现的词对相关度的影响。</small></label>
                <label>长度归一化 b<a-input-number v-model:value="draft.b" aria-label="长度归一化 b" :min="0" :max="1" :step="0.05" /><small>越接近 1，越强调不同长度内容之间的平衡。</small></label>
              </fieldset>
            </a-spin>
            <a-alert v-if="saved && !validConfig" type="warning" message="请填写范围内的有效参数" class="notice" />
            <div class="config-actions"><a-button :disabled="!saved || settingsLoading || saving" @click="Object.assign(draft, defaults)">恢复默认</a-button><a-button type="primary" :loading="saving" :disabled="!dirty || !validConfig || settingsError" @click="saveSettings">保存配置</a-button></div>
            <div v-if="saved" class="saved-summary">已保存：{{ saved.limit }} 块 · {{ saved.token_budget }} tokens<br />k1 {{ saved.k1 }} · b {{ saved.b }}</div>
          </section>

          <div class="test-column">
            <section class="memory-panel">
              <div class="panel-title"><ExperimentOutlined /><h2>测试召回</h2></div>
              <p class="muted">输入一个问题，查看记忆如何进入上下文。测试不会增加使用次数。</p>
              <label class="query-label" for="memory-query">测试问题</label>
              <a-textarea id="memory-query" v-model:value="query" placeholder="例如：之前的 Python 项目是如何配置的？" :auto-size="{ minRows: 3, maxRows: 8 }" :maxlength="20000" />
              <div class="test-actions"><span class="muted">{{ dirty ? '使用未保存草稿测试' : '使用已保存配置测试' }}</span><a-button type="primary" :loading="testing" :disabled="!query.trim() || !saved || !validConfig || settingsError" @click="testRecall">测试召回</a-button></div>
              <a-alert v-if="testError" type="error" show-icon message="测试失败，请重试" class="notice"><template #action><a-button size="small" @click="testRecall">重试</a-button></template></a-alert>
            </section>

            <section v-if="result" class="memory-panel result-panel">
              <div class="panel-title"><SearchOutlined /><h2>召回结果</h2></div>
              <a-alert v-if="staleResult" type="warning" show-icon message="问题或参数已改变，以下为上次测试结果" class="notice" />
              <p class="tested-query">{{ testedQuery }}</p>
              <div class="result-stats"><div><strong>{{ result.corpus_count }}</strong><span>有效记忆</span></div><div><strong>{{ result.matched_count }}</strong><span>关键词匹配</span></div><div><strong>{{ result.selected.length }}</strong><span>最终入选</span></div><div><strong>{{ result.token_count }}</strong><span>估算 tokens</span></div></div>
              <p class="muted result-config">本次参数：{{ result.config.limit }} 块 / {{ result.config.token_budget }} tokens / k1 {{ result.config.k1 }} / b {{ result.config.b }}</p>
              <a-empty v-if="!result.selected.length" :description="emptyMessage" class="empty-state" />
              <div v-for="hit in result.selected" :key="hit.block_id" class="recall-hit">
                <div class="hit-title"><strong>#{{ hit.rank }} · {{ kindNames[hit.section_kind] || hit.section_kind }}</strong><span>BM25 {{ score(hit.score) }}</span><a-button size="small" @click="openDetail(hit.block_id)">详情</a-button></div>
                <div class="md-body" v-html="renderMarkdown(hit.content)"></div>
                <p class="muted source-reference">{{ hit.room_name }} / {{ hit.conversation_name }} · 约 {{ hit.token_count }} tokens<br />{{ hit.file_path }}:{{ hit.start_line }}–{{ hit.end_line }}</p>
              </div>
              <a-collapse ghost class="diagnostic-sections">
                <a-collapse-panel key="diagnostics" header="候选筛选诊断">
                  <p class="muted">分数为 BM25 相关度，不代表概率。</p>
                  <a-alert v-if="result.diagnostics_truncated" type="info" message="诊断仅展示前 100 条候选；所有已选块均已展示在上方。" class="notice" />
                  <div class="diagnostics-scroll"><table class="diagnostics-table"><thead><tr><th>排名</th><th>候选内容</th><th>BM25 分数</th><th>结果</th></tr></thead><tbody><tr v-for="row in result.diagnostics" :key="row.block_id"><td>{{ row.rank }}</td><td><button class="text-link" @click="openDetail(row.block_id)">{{ row.summary }}</button></td><td>{{ score(row.score) }}</td><td><a-tag :color="row.reason === 'selected' ? 'green' : 'default'">{{ reasonNames[row.reason] }}</a-tag></td></tr></tbody></table></div>
                  <a-empty v-if="!result.diagnostics.length" description="没有匹配候选" />
                </a-collapse-panel>
                <a-collapse-panel key="context" header="最终 L1 上下文原文">
                  <pre v-if="result.context" class="raw-text">{{ result.context }}</pre><a-empty v-else description="本次不注入长期记忆" />
                </a-collapse-panel>
              </a-collapse>
            </section>
            <div v-else-if="!testing" class="test-placeholder"><ExperimentOutlined /><p>运行一次测试，查看召回结果与上下文。</p></div>
          </div>
        </div>
      </a-tab-pane>
      <a-tab-pane key="generate" tab="记忆生成"><MemoryProcessingPanel :active="tab === 'generate'" /></a-tab-pane>
    </a-tabs>

    <a-drawer :open="drawer" title="记忆详情" width="min(760px, 100vw)" @close="closeDrawer">
      <a-spin :spinning="detailLoading">
        <a-result v-if="detailError" status="warning" title="无法加载记忆详情"><template #extra><a-button @click="openDetail(selectedId)">重试</a-button></template></a-result>
        <template v-if="detail">
          <a-tag :color="statusColor(detail.item.status)">{{ statusNames[detail.item.status] }}</a-tag><a-tag>{{ kindNames[detail.item.section_kind] }}</a-tag><a-tag>版本 {{ detail.item.version }}</a-tag>
          <h3 v-if="detail.item.section_kind === 'extracted'" class="detail-section">提取正文</h3>
          <div class="detail-content md-body" v-html="renderMarkdown(detail.item.content)"></div>
          <a-descriptions title="来源与元信息" size="small" bordered :column="detailColumns">
            <a-descriptions-item label="房间">{{ detail.item.room_name }}</a-descriptions-item><a-descriptions-item label="会话">{{ detail.item.conversation_name }}</a-descriptions-item>
            <a-descriptions-item label="类型">{{ detail.item.memory_type }}</a-descriptions-item><a-descriptions-item label="标签">{{ detail.item.tags.join('、') || '—' }}</a-descriptions-item>
            <a-descriptions-item label="估算 token">{{ detail.item.token_count }}</a-descriptions-item><a-descriptions-item label="使用次数">{{ detail.item.usage_count }}</a-descriptions-item>
            <a-descriptions-item label="更新于">{{ formatDate(detail.item.updated_at) }}</a-descriptions-item><a-descriptions-item label="过期时间">{{ detail.item.expires_at ? formatDate(detail.item.expires_at) : '长期有效' }}</a-descriptions-item>
            <a-descriptions-item label="运行状态">{{ detail.item.run_status }}</a-descriptions-item><a-descriptions-item label="行号">{{ detail.item.start_line }}–{{ detail.item.end_line }}</a-descriptions-item>
            <a-descriptions-item label="块 ID" :span="detailColumns"><code class="break-anywhere">{{ detail.item.block_id }}</code></a-descriptions-item>
            <a-descriptions-item label="文件" :span="detailColumns"><code class="break-anywhere">{{ detail.item.file_path }}</code></a-descriptions-item>
          </a-descriptions>
          <section v-if="detail.item.evidence_refs?.length" class="detail-section">
            <h3>原文证据 · {{ detail.item.evidence_refs.length }} 条</h3>
            <p class="muted">行号定位原始 run 中的证据，提取正文与原文不要求逐字相同。</p>
            <div v-for="(ref, index) in detail.item.evidence_refs" :key="ref.candidate_id || index" class="evidence-item">
              <strong>{{ ref.room_name }} / {{ ref.conversation_name }}</strong>
              <p class="muted break-anywhere">{{ ref.file_path }}:{{ ref.start_line }}–{{ ref.end_line }} · {{ ref.run_status }}<span v-if="ref.section_kind === 'think'"> · 历史思考记录</span></p>
              <p v-if="ref.event?.event_id" class="muted break-anywhere">事件 {{ ref.event.event_id }} · agent {{ ref.event.agent_id }}</p>
              <a-button size="small" :loading="sourceLoading && sourceRange?.candidate_id === ref.candidate_id" @click="loadSource(ref)">查看此证据 MD</a-button>
            </div>
          </section>
          <a-collapse v-if="detail.item.metadata?.structure || detail.item.metadata?.classifications" class="detail-section">
            <a-collapse-panel v-if="detail.item.metadata.structure" key="structure" header="结构化提取结果"><pre class="raw-text">{{ JSON.stringify(detail.item.metadata.structure, null, 2) }}</pre></a-collapse-panel>
            <a-collapse-panel v-if="detail.item.metadata.classifications" key="classifications" header="各证据的筛选与分类概率">
              <div v-for="item in detail.item.metadata.classifications" :key="item.candidate_id" class="evidence-item">
                <p class="muted break-anywhere">候选 {{ item.candidate_id }}</p><p>Noul：{{ item.noul.noul }} · 主类别：{{ categoryNames[item.choice.category] }} · Choice 置信度：{{ item.choice.confidence }}</p>
                <p v-for="(value, category) in item.choice.probabilities" :key="category">{{ categoryNames[category] }}：{{ (value * 100).toFixed(1) }}%</p>
                <p class="muted">{{ item.noul.model }} / {{ item.noul.prompt_version }}<br>{{ item.choice.model }} / {{ item.choice.prompt_version }}</p>
              </div>
            </a-collapse-panel>
          </a-collapse>
          <section v-if="detail.related.length" class="detail-section"><h3>版本与派生关系</h3><div v-for="related in detail.related" :key="related.block_id" class="related-item"><span>{{ relationship(related) }}</span><button class="text-link" @click="openDetail(related.block_id)">{{ related.summary }}</button><a-tag>{{ statusNames[related.status] }}</a-tag></div></section>
          <section class="detail-section"><a-button :loading="sourceLoading" @click="loadSource"><template #icon><FileTextOutlined /></template>{{ source ? '刷新来源 MD' : '查看来源 MD' }}</a-button>
            <a-alert v-if="sourceError" class="notice" type="error" message="来源文件读取失败，可重新点击查看" />
            <p v-if="source" class="muted break-anywhere">{{ source.file_path }} · 原文证据 {{ sourceRange.start_line }}–{{ sourceRange.end_line }} 行</p>
            <div v-if="source" class="source-lines"><div v-for="(line, index) in source.content.split('\n')" :key="index" class="source-line" :class="{ 'source-line--selected': index + 1 >= sourceRange.start_line && index + 1 <= sourceRange.end_line }"><span>{{ index + 1 }}</span><code>{{ line || ' ' }}</code></div></div>
          </section>
        </template>
      </a-spin>
    </a-drawer>
  </main>
</template>

<style scoped>
.memory-workspace { width: min(1400px, 100%); margin: 0 auto; padding: 28px 32px 48px; color: var(--text); }
.memory-heading { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.heading-icon { display: grid; place-items: center; width: 52px; height: 52px; border-radius: 16px; color: var(--accent, #3578ff); background: #eaf1ff; font-size: 26px; flex-shrink: 0; }
.eyebrow { font-size: 10px; letter-spacing: 2px; font-weight: 750; color: var(--muted); }
h1 { font-size: 26px; margin: 2px 0 5px; letter-spacing: -.5px; }
.memory-heading p { margin: 0; color: var(--muted); font-size: 13px; }
.account-tag { margin-left: auto; }
.memory-panel { background: rgba(255,255,255,.9); border: 1px solid rgba(112,135,169,.17); border-radius: 18px; padding: 24px; box-shadow: 0 6px 24px rgba(27,39,66,.035); min-width: 0; }
.memory-tabs :deep(.ant-tabs-nav) { margin-bottom: 20px; }
.filter-grid { display: grid; grid-template-columns: minmax(200px, 1.6fr) repeat(3, minmax(120px, 1fr)) auto; gap: 12px; align-items: end; }
label { display: grid; gap: 7px; font-size: 12px; font-weight: 650; color: var(--muted); }
.filter-grid :deep(.ant-select) { width: 100%; }
.list-heading { display: flex; justify-content: space-between; align-items: center; margin: 22px 0 12px; font-size: 13px; color: var(--muted); }
.list-heading strong { color: var(--text); }
.memory-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; min-height: 100px; }
.memory-card { text-align: left; width: 100%; min-width: 0; cursor: pointer; color: inherit; font: inherit; padding: 18px; border: 1px solid #e4eaf3; border-radius: 12px; background: #fff; transition: border-color .15s, box-shadow .15s; }
.memory-card:hover, .memory-card:focus-visible { border-color: var(--accent, #3578ff); box-shadow: 0 5px 18px #3578ff12; outline: none; }
.card-top, .card-date { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.kind-label { color: var(--muted); font-size: 12px; }
.card-summary { font-size: 14px; line-height: 1.7; min-height: 48px; margin: 14px 0 12px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px; }
.card-source { font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: #637087; margin: 12px 0; }
.card-date { border-top: 1px solid #f0f3f8; padding-top: 12px; color: var(--muted); font-size: 11px; }
.card-date span { color: var(--accent, #3578ff); white-space: nowrap; }
.memory-pagination { display: flex; justify-content: flex-end; flex-wrap: wrap; margin-top: 22px; }
.empty-state { padding: 42px 0; }
.retrieval-layout { display: grid; grid-template-columns: 320px minmax(0,1fr); gap: 22px; align-items: start; }
.test-column { display: grid; gap: 20px; min-width: 0; }
.panel-title { display: flex; align-items: center; gap: 9px; color: var(--accent, #3578ff); }
.panel-title h2 { color: var(--text); font-size: 17px; margin: 0; flex: 1; }
.panel-title :deep(.ant-tag) { margin: 0; }
.muted { color: var(--muted); font-size: 12px; line-height: 1.7; }
.config-fields { padding: 0; margin: 20px 0; border: 0; display: grid; gap: 18px; min-width: 0; }
.config-fields :deep(.ant-input-number) { width: 100%; }
.config-fields small { font-size: 11px; line-height: 1.6; font-weight: 400; }
.bm25-heading { padding-top: 16px; border-top: 1px solid #e9edf4; color: var(--text); font-weight: 650; font-size: 12px; }
.config-actions, .test-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 18px; }
.saved-summary { margin-top: 16px; border-top: 1px solid #edf1f6; padding-top: 14px; color: var(--muted); font-size: 11px; line-height: 1.8; }
.query-label { margin: 18px 0 8px; }
.notice { margin: 14px 0; }
.test-placeholder { color: var(--muted); text-align: center; padding: 55px 20px; font-size: 13px; }
.test-placeholder :deep(.anticon) { font-size: 30px; opacity: .45; }
.tested-query { font-size: 13px; color: var(--muted); overflow-wrap: anywhere; white-space: pre-wrap; }
.result-stats { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; background: #f5f8fd; padding: 16px; border-radius: 12px; margin: 18px 0 10px; }
.result-stats div { display: grid; gap: 4px; }
.result-stats strong { font-size: 23px; font-variant-numeric: tabular-nums; font-weight: 650; }
.result-stats span { color: var(--muted); font-size: 11px; }
.result-config { margin-bottom: 20px; }
.recall-hit { padding: 18px 0; border-top: 1px solid #e8edf4; }
.hit-title { display: flex; align-items: center; gap: 12px; font-size: 12px; margin-bottom: 14px; }
.hit-title strong { flex: 1; }
.hit-title > span { color: var(--accent, #3578ff); white-space: nowrap; }
.source-reference { overflow-wrap: anywhere; margin-bottom: 0; }
.diagnostics-scroll { overflow-x: auto; }
.diagnostics-table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 430px; }
.diagnostics-table th { text-align: left; color: var(--muted); font-weight: 500; white-space: nowrap; }
.diagnostics-table td, .diagnostics-table th { padding: 10px 8px; border-bottom: 1px solid #edf1f6; }
.diagnostics-table .text-link { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-width: 100px; }
.text-link { background: none; border: 0; padding: 0; color: var(--accent, #3578ff); font: inherit; cursor: pointer; text-align: left; overflow-wrap: anywhere; }
.text-link:hover { text-decoration: underline; }
.raw-text { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.8; background: #f5f7fb; border-radius: 8px; padding: 16px; }
.detail-content { margin: 20px 0 28px; overflow-wrap: anywhere; }
.detail-section { margin-top: 26px; }
.evidence-item { padding: 14px 0; border-bottom: 1px solid #edf1f6; font-size: 12px; overflow-wrap: anywhere; }
.detail-section h3 { font-size: 15px; }
.break-anywhere { overflow-wrap: anywhere; }
.related-item { display: flex; align-items: start; gap: 10px; margin: 12px 0; font-size: 12px; }
.related-item > span { white-space: nowrap; }
.related-item .text-link { flex: 1; }
.source-lines { margin-top: 16px; font-size: 12px; background: #f7f9fc; padding: 12px 0; border: 1px solid #edf1f6; border-radius: 8px; }
.source-line { display: grid; grid-template-columns: 42px minmax(0,1fr); line-height: 1.8; }
.source-line > span { color: #8390a5; padding: 0 10px; text-align: right; user-select: none; }
.source-line code { white-space: pre-wrap; overflow-wrap: anywhere; padding-right: 12px; }
.source-line--selected { background: #e7f0ff; }
@media (max-width: 1050px) { .filter-grid { grid-template-columns: repeat(3,minmax(0,1fr)); } .search-field { grid-column: span 2; } .retrieval-layout { grid-template-columns: 280px minmax(0,1fr); gap: 14px; } .memory-workspace { padding: 24px 20px; } .memory-panel { padding: 20px; } }
@media (max-width: 720px) { .memory-workspace { padding: 18px 12px 32px; } .memory-heading { gap: 12px; align-items: start; } .heading-icon { width: 42px; height: 42px; font-size: 22px; } h1 { font-size: 22px; } .account-tag { display: none; } .memory-heading p { font-size: 12px; } .memory-panel { padding: 16px; border-radius: 14px; } .filter-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } .memory-grid, .retrieval-layout { grid-template-columns: minmax(0,1fr); } .config-fields { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 14px; } .bm25-heading { grid-column: 1 / -1; } .result-stats { padding: 12px; } .result-stats strong { font-size: 20px; } .memory-pagination { justify-content: center; } .card-date { font-size: 10px; } .test-actions > span { max-width: 55%; } }
</style>
