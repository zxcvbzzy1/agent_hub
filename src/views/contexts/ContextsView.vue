<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import JsonBlock from '@/components/workflow/JsonBlock.vue'
import { useContextsStore } from '@/stores/contexts'

const contexts = useContextsStore()
const lookupId = ref('default_executor')
const selectedProvider = ref('user_prompt')
const selectedTemplate = ref('executor')
const form = reactive({
  name: '自定义执行者上下文',
  kind: 'executor',
  provider_config: [],
})
const defaultAvailableFields = ['system', 'search', 'memory', 'write_agent', 'human']

const contextColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '类型', dataIndex: 'kind', key: 'kind', width: 100 },
  { title: 'Providers', dataIndex: 'provider_count', key: 'provider_count', width: 110 },
  { title: 'Loaded', dataIndex: 'engine_loaded', key: 'engine_loaded', width: 90 },
  { title: '操作', key: 'actions', width: 90 },
]
const protectedContextIds = new Set(['default_executor', 'default_planner', 'default_step'])

const providerCatalog = computed(() => contexts.catalogData?.providers || [])
const strategyCatalog = computed(() => contexts.catalogData?.strategies || [])
const templateMap = computed(() => contexts.catalogData?.templates || {})
const payloadPreview = computed(() => ({
  name: form.name,
  kind: form.kind,
  provider_config: form.provider_config,
}))

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function loadTemplate(kind = selectedTemplate.value) {
  const template = templateMap.value[kind] || []
  form.kind = kind
  form.name = kind === 'planner' ? '自定义编排上下文' : kind === 'step' ? '自定义步骤上下文' : '自定义执行者上下文'
  form.provider_config = clone(template)
}

function defaultStrategy(type = 'full_history') {
  const defaults = {
    full_history: { type: 'full_history' },
    latest_only: { type: 'latest_only' },
    recency: { type: 'recency', keep_last: 10 },
    token_budget: { type: 'token_budget', token_limit: 4000 },
    summarize: { type: 'summarize', threshold: 800 },
    filter_by_tool: { type: 'filter_by_tool', tool_names: [] },
  }
  return clone(defaults[type] || defaults.full_history)
}

function defaultProvider(providerId = selectedProvider.value) {
  const memoryStrategy = { pipeline: [defaultStrategy('full_history')] }
  const defaults = {
    user_prompt: { provider_id: 'user_prompt', enabled: true, params: {} },
    state: { provider_id: 'state', enabled: true, params: {} },
    available_tools: {
      provider_id: 'available_tools',
      enabled: true,
      params: { available_fields: [...defaultAvailableFields] },
    },
    history: {
      provider_id: 'history',
      enabled: true,
      params: { memory_field: 'agent_history', strategy_config: clone(memoryStrategy) },
    },
    tool_output: {
      provider_id: 'tool_output',
      enabled: true,
      params: { memory_field: 'tool_respond', strategy_config: clone(memoryStrategy) },
    },
    executor_status: { provider_id: 'executor_status', enabled: true, params: {} },
    available_executors: { provider_id: 'available_executors', enabled: true, params: {} },
    plan_observations: { provider_id: 'plan_observations', enabled: true, params: {} },
    plan_step_prompt: { provider_id: 'plan_step_prompt', enabled: true, params: {} },
  }
  return clone(defaults[providerId] || defaults.user_prompt)
}

function addProvider() {
  form.provider_config.push(defaultProvider())
}

function removeProvider(index) {
  form.provider_config.splice(index, 1)
}

function moveProvider(index, direction) {
  const nextIndex = index + direction
  if (nextIndex < 0 || nextIndex >= form.provider_config.length) return
  const [item] = form.provider_config.splice(index, 1)
  form.provider_config.splice(nextIndex, 0, item)
}

function ensureStrategyConfig(provider) {
  provider.params ||= {}
  provider.params.strategy_config ||= { pipeline: [defaultStrategy('full_history')] }
  provider.params.strategy_config.pipeline ||= [defaultStrategy('full_history')]
  return provider.params.strategy_config.pipeline
}

function addStrategy(provider) {
  ensureStrategyConfig(provider).push(defaultStrategy('recency'))
}

function removeStrategy(provider, index) {
  ensureStrategyConfig(provider).splice(index, 1)
}

function setStrategyType(strategy, type) {
  Object.keys(strategy).forEach((key) => delete strategy[key])
  Object.assign(strategy, defaultStrategy(type))
}

async function create() {
  if (!form.provider_config.length) {
    message.warning('至少需要一个 provider')
    return
  }
  const item = await contexts.createContext(clone(payloadPreview.value))
  lookupId.value = item.context_id
  message.success('上下文引擎已创建')
}

async function lookup() {
  await contexts.getContext(lookupId.value)
}

async function selectContext(record) {
  lookupId.value = record.context_id
  await contexts.getContext(record.context_id)
}

function isProtectedContext(contextId) {
  return protectedContextIds.has(contextId)
}

function confirmDeleteContext(record) {
  Modal.confirm({
    title: '删除 ContextEngine',
    content: `确认删除「${record.name || record.context_id}」吗？被 Agent 或 Run 引用时后端会拒绝删除。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await contexts.deleteContext(record.context_id)
      if (lookupId.value === record.context_id) {
        lookupId.value = contexts.items[0]?.context_id || 'default_executor'
      }
      message.success('ContextEngine 已删除')
    },
  })
}

onMounted(async () => {
  await Promise.all([contexts.fetchCatalog(), contexts.fetchContexts()])
  loadTemplate('executor')
})
</script>

<template>
  <section class="page-stack">
    
    <div class="page-heading">
      <div>
        <span class="eyebrow">Context Engine</span>
        <h1>上下文供应商与策略管道</h1>
      </div>
      <a-space wrap>
        <a-select v-model:value="selectedTemplate" style="width: 160px" @change="loadTemplate">
          <a-select-option value="executor">executor 模板</a-select-option>
          <a-select-option value="planner">planner 模板</a-select-option>
          <a-select-option value="step">step 模板</a-select-option>
        </a-select>
        <a-button @click="contexts.fetchContexts">刷新列表</a-button>
      </a-space>
    </div>

    <div class="context-console-grid">
      <div class="executor-column">
        <a-card class="panel-card" title="Context Engines" :bordered="false">
          <a-table
            :columns="contextColumns"
            :data-source="contexts.items"
            :loading="contexts.loading"
            row-key="context_id"
            size="small"
            :pagination="{ pageSize: 8 }"
            :custom-row="record => ({ onClick: () => selectContext(record) })"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'kind'">
                <a-tag>{{ record.kind }}</a-tag>
              </template>
              <template v-if="column.key === 'engine_loaded'">
                <a-tag :color="record.engine_loaded ? 'green' : 'default'">
                  {{ record.engine_loaded ? 'loaded' : 'cold' }}
                </a-tag>
              </template>
              <template v-if="column.key === 'actions'">
                <a-button
                  size="small"
                  danger
                  :disabled="isProtectedContext(record.context_id)"
                  @click.stop="confirmDeleteContext(record)"
                >
                  删除
                </a-button>
              </template>
            </template>
          </a-table>
          <a-input-search v-model:value="lookupId" class="mt-16" enter-button="查询" @search="lookup" />
        </a-card>
        <a-card class="panel-card" title="当前配置 / 查询结果" :bordered="false">
          <a-tabs>
            <a-tab-pane key="payload" tab="Payload">
              <JsonBlock :value="payloadPreview" />
            </a-tab-pane>
            <a-tab-pane key="current" tab="Current">
              <JsonBlock :value="contexts.current || { context_id: lookupId }" />
            </a-tab-pane>
          </a-tabs>
        </a-card>

         <a-card class="panel-card" title="Catalog" :bordered="false">
          <a-tabs>
            <a-tab-pane key="providers" tab="Providers">
              <JsonBlock :value="providerCatalog" />
            </a-tab-pane>
            <a-tab-pane key="strategies" tab="Strategies">
              <JsonBlock :value="strategyCatalog" />
            </a-tab-pane>
          </a-tabs>
        </a-card>
      </div>
      <a-card class="panel-card" title="Engine Builder" :bordered="false">
        <a-form layout="vertical" @finish="create">
          <div class="form-pair">
            <a-form-item label="名称">
              <a-input v-model:value="form.name" />
            </a-form-item>
            <a-form-item label="类型">
              <a-select v-model:value="form.kind" style="width: 160px">
                <a-select-option value="executor">executor</a-select-option>
                <a-select-option value="planner">planner</a-select-option>
                <a-select-option value="step">step</a-select-option>
              </a-select>
            </a-form-item>
          </div>

          <div class="context-add-row">
            <a-select v-model:value="selectedProvider" style="min-width: 220px">
              <a-select-option
                v-for="provider in providerCatalog"
                :key="provider.provider_id"
                :value="provider.provider_id"
              >
                {{ provider.provider_id }}
              </a-select-option>
            </a-select>
            <a-button @click="addProvider">添加 Provider</a-button>
          </div>

          <div class="provider-stack">
            <a-card
              v-for="(provider, index) in form.provider_config"
              :key="`${provider.provider_id}-${index}`"
              class="context-provider-card"
              :bordered="false"
            >
              <div class="card-title-row">
                <a-space wrap>
                  <a-tag color="blue">#{{ index + 1 }}</a-tag>
                  <a-select v-model:value="provider.provider_id" style="width: 220px">
                    <a-select-option
                      v-for="entry in providerCatalog"
                      :key="entry.provider_id"
                      :value="entry.provider_id"
                    >
                      {{ entry.provider_id }}
                    </a-select-option>
                  </a-select>
                  <a-switch v-model:checked="provider.enabled" checked-children="on" un-checked-children="off" />
                </a-space>
                <a-space>
                  <a-button size="small" @click="moveProvider(index, -1)">上移</a-button>
                  <a-button size="small" @click="moveProvider(index, 1)">下移</a-button>
                  <a-button size="small" danger @click="removeProvider(index)">删除</a-button>
                </a-space>
              </div>

              <a-form-item v-if="provider.provider_id === 'available_tools'" label="可用工具领域">
                <a-select v-model:value="provider.params.available_fields" mode="tags">
                  <a-select-option value="system">system</a-select-option>
                  <a-select-option value="write_agent">write_agent</a-select-option>
                  <a-select-option value="human">human</a-select-option>
                  <a-select-option value="memory">memory</a-select-option>
                  <a-select-option value="search">search</a-select-option>
                </a-select>
              </a-form-item>

              <template v-if="['history', 'tool_output'].includes(provider.provider_id)">
                <a-form-item label="Memory Field">
                  <a-select v-model:value="provider.params.memory_field">
                    <a-select-option value="agent_history">agent_history</a-select-option>
                    <a-select-option value="tool_respond">tool_respond</a-select-option>
                  </a-select>
                </a-form-item>

                <div class="strategy-stack">
                  <div class="card-title-row">
                    <strong>Strategy Pipeline</strong>
                    <a-button size="small" @click="addStrategy(provider)">添加策略</a-button>
                  </div>
                  <div
                    v-for="(strategy, strategyIndex) in ensureStrategyConfig(provider)"
                    :key="`${provider.provider_id}-strategy-${strategyIndex}`"
                    class="strategy-row"
                  >
                    <a-select
                      :value="strategy.type"
                      style="width: 180px"
                      @change="type => setStrategyType(strategy, type)"
                    >
                      <a-select-option
                        v-for="entry in strategyCatalog"
                        :key="entry.type"
                        :value="entry.type"
                      >
                        {{ entry.type }}
                      </a-select-option>
                    </a-select>
                    <a-input-number
                      v-if="strategy.type === 'recency'"
                      v-model:value="strategy.keep_last"
                      addon-before="keep_last"
                      :min="1"
                    />
                    <a-input-number
                      v-if="strategy.type === 'token_budget'"
                      v-model:value="strategy.token_limit"
                      addon-before="token_limit"
                      :min="1"
                    />
                    <a-input-number
                      v-if="strategy.type === 'summarize'"
                      v-model:value="strategy.threshold"
                      addon-before="threshold"
                      :min="1"
                    />
                    <a-select
                      v-if="strategy.type === 'filter_by_tool'"
                      v-model:value="strategy.tool_names"
                      mode="tags"
                      style="min-width: 220px;"
                      placeholder="tool names"
                    />
                    <a-button size="small" danger @click="removeStrategy(provider, strategyIndex)">删除</a-button>
                  </div>
                </div>
              </template>
            </a-card>
          </div>

          <a-button type="primary" html-type="button" :loading="contexts.loading" style="margin-top: 16px;" @click="create">
            创建 ContextEngine
          </a-button>
        </a-form>
      </a-card>
    </div>
  </section>
</template>
