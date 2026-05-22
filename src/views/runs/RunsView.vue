<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import EventTimeline from '@/components/workflow/EventTimeline.vue'
import ExecutorEventPanel from '@/components/workflow/ExecutorEventPanel.vue'
import JsonBlock from '@/components/workflow/JsonBlock.vue'
import { useAgentsStore } from '@/stores/agents'
import { useContextsStore } from '@/stores/contexts'
import { useRunsStore } from '@/stores/runs'

const agents = useAgentsStore()
const contexts = useContextsStore()
const runs = useRunsStore()
const lookupId = ref('')
const selectedExecutor = ref('')
const form = reactive({
  prompt: '请分析当前任务并给出执行结果',
  planner_agent_id: 'default_planner',
  executor_agent_ids: ['default_executor'],
  context_id: 'default_step',
  max_replan_rounds: 3,
  auto_start: true,
})

const runColumns = [
  { title: 'Run ID', dataIndex: 'run_id', key: 'run_id', width: 180 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 110 },
  { title: 'Prompt', dataIndex: 'prompt', key: 'prompt' },
  { title: 'Planner', dataIndex: 'planner_agent_id', key: 'planner_agent_id', width: 160 },
  { title: 'Executors', dataIndex: 'executor_agent_ids', key: 'executor_agent_ids', width: 110 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
]

const plannerAgents = computed(() => agents.items.filter((item) => item.agent_type === 'planner'))
const executorAgents = computed(() => agents.items.filter((item) => item.agent_type === 'executor'))
const stepContexts = computed(() => contexts.items.filter((item) => item.kind === 'step'))
const events = computed(() => {
  const runId = runs.current?.run_id
  return runId ? runs.eventsByRun[runId] || [] : []
})

function statusColor(status) {
  if (status === 'failed' || status === 'cancelled') return 'red'
  if (status === 'finished') return 'green'
  if (status === 'running') return 'blue'
  return 'gold'
}

function shortText(value = '', length = 58) {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

function formatTime(value) {
  return value ? new Date(value * 1000).toLocaleString() : '-'
}

function applyDefaults() {
  form.planner_agent_id = plannerAgents.value.find((item) => item.agent_id === 'default_planner')?.agent_id
    || plannerAgents.value[0]?.agent_id
    || form.planner_agent_id
  form.executor_agent_ids = [
    executorAgents.value.find((item) => item.agent_id === 'default_executor')?.agent_id
      || executorAgents.value[0]?.agent_id
      || 'default_executor',
  ].filter(Boolean)
  form.context_id = stepContexts.value.find((item) => item.context_id === 'default_step')?.context_id
    || stepContexts.value[0]?.context_id
    || form.context_id
}

async function createRun() {
  if (!form.executor_agent_ids.length) {
    message.warning('至少选择一个执行者 Agent')
    return
  }
  const item = await runs.createRun({ ...form, executor_agent_ids: [...form.executor_agent_ids] })
  lookupId.value = item.run_id
  selectedExecutor.value = item.executor_agent_ids?.[0] || ''
  runs.connect(item.run_id)
  message.success('Run 已创建')
}

async function selectRun(record) {
  const item = await runs.fetchRun(record.run_id)
  lookupId.value = item.run_id
  selectedExecutor.value = item.executor_agent_ids?.[0] || ''
  runs.connect(item.run_id)
}

async function lookup() {
  if (!lookupId.value) return
  const item = await runs.fetchRun(lookupId.value)
  selectedExecutor.value = item.executor_agent_ids?.[0] || ''
  runs.connect(item.run_id)
}

function openStandalone() {
  if (runs.current?.run_id) {
    window.open(`/runs/${runs.current.run_id}/events`, '_blank')
  }
}

async function refreshAll() {
  await Promise.all([agents.fetchAgents(), contexts.fetchContexts(), runs.fetchRuns()])
  applyDefaults()
}

onMounted(async () => {
  await refreshAll()
})
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <span class="eyebrow">Run Orchestration</span>
        <h1>编排运行</h1>
      </div>
      <a-space wrap>
        <a-button @click="refreshAll">刷新资源</a-button>
        <a-button @click="openStandalone" :disabled="!runs.current">独立事件页</a-button>
      </a-space>
    </div>

    <div class="run-grid">
      <div>
        <a-card class="panel-card" title="创建 Run" :bordered="false" style="margin-bottom: 16px;">
          <a-form layout="vertical" @finish="createRun">
            <a-form-item label="Prompt">
              <a-textarea v-model:value="form.prompt" :rows="5" />
            </a-form-item>
            <div class="form-pair">
              <a-form-item label="Planner Agent">
                <a-select v-model:value="form.planner_agent_id" show-search option-filter-prop="label">
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
              <a-form-item label="Step Context">
                <a-select v-model:value="form.context_id" show-search option-filter-prop="label">
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
            </div>
            <a-form-item label="Executor Agents">
              <a-select
                v-model:value="form.executor_agent_ids"
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
            <div class="form-pair">
              <a-form-item label="Max Replan">
                <a-input-number v-model:value="form.max_replan_rounds" :min="0" />
              </a-form-item>
              <a-form-item label="自动启动">
                <a-switch v-model:checked="form.auto_start" />
              </a-form-item>
            </div>
            <a-button type="primary" html-type="submit" :loading="runs.loading">创建</a-button>
          </a-form>
        </a-card>

        <a-card class="panel-card" title="Run 状态" :bordered="false">
          <a-input-search v-model:value="lookupId" enter-button="查询并连接 SSE" @search="lookup" />
          <a-descriptions v-if="runs.current" class="mt-16" :column="1" size="small">
            <a-descriptions-item label="Run ID">{{ runs.current.run_id }}</a-descriptions-item>
            <a-descriptions-item label="状态">
              <a-tag :color="statusColor(runs.current.status)">{{ runs.current.status }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="Planner">{{ runs.current.planner_agent_id }}</a-descriptions-item>
            <a-descriptions-item label="Executors">{{ runs.current.executor_agent_ids?.join(', ') }}</a-descriptions-item>
            <a-descriptions-item label="Final">{{ runs.current.final || '-' }}</a-descriptions-item>
          </a-descriptions>
          <JsonBlock class="mt-16" :value="runs.current || { status: 'waiting' }" />
        </a-card>
      </div>

      <a-card class="panel-card" title="Run 列表" :bordered="false" >
        <a-table
          :columns="runColumns"
          :data-source="runs.items"
          row-key="run_id"
          size="small"
          :loading="runs.loading"
          :pagination="{ pageSize: 6 }"
          :custom-row="record => ({ onClick: () => selectRun(record) })"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'run_id'">
              <a-button type="link" size="small" @click.stop="selectRun(record)">
                {{ record.run_id.slice(0, 8) }}
              </a-button>
            </template>
            <template v-if="column.key === 'status'">
              <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
            </template>
            <template v-if="column.key === 'prompt'">
              {{ shortText(record.prompt) }}
            </template>
            <template v-if="column.key === 'executor_agent_ids'">
              <a-tag>{{ record.executor_agent_ids?.length || 0 }}</a-tag>
            </template>
            <template v-if="column.key === 'created_at'">
              {{ formatTime(record.created_at) }}
            </template>
          </template>
        </a-table>
      </a-card>
    </div>

    <div class="event-workbench">
      <a-card class="panel-card" title="总体事件流" :bordered="false">
        <EventTimeline :events="events" />
      </a-card>
      <div>
        <a-card class="panel-card" title="执行者选择" :bordered="false" style="margin-bottom: 16px;">
          <a-select v-model:value="selectedExecutor" style="width: 100%">
            <a-select-option value="">全部</a-select-option>
            <a-select-option v-for="id in runs.current?.executor_agent_ids || []" :key="id" :value="id">
              {{ id }}
            </a-select-option>
          </a-select>
        </a-card>
        <ExecutorEventPanel :events="events" :executor-id="selectedExecutor" />
      </div>
    </div>
  </section>
</template>
