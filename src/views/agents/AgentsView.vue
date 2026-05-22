<script setup>
import { computed, onMounted, reactive, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useAgentsStore } from '@/stores/agents'
import { useContextsStore } from '@/stores/contexts'

const agents = useAgentsStore()
const contexts = useContextsStore()
const form = reactive({
  name: '新的执行者',
  agent_type: 'executor',
  context_id: 'default_executor',
  description: '',
  role_prompt: `
你是一个执行者

## 输出格式
用 JSON 严格按以下格式回复：
{{
  "think": "你的思考过程",
  "tool_calls": [
    {{
      "tool_name": "工具名",
      "arguments": {{"参数名": "参数值"}},
      "reasoning": "为什么调用这个工具"
    }}
  ],
  "is_finished": false
}}

## 任务完成时输出
{{
  "think": "...",
  "tool_calls": [],
  "is_finished": true,
  "finish_reason": "完成原因",
  "final": "最终结果"
}}
  `,
})

const contextOptions = computed(() => contexts.items)
const matchingContexts = computed(() => {
  const preferredKind = form.agent_type === 'planner' ? 'planner' : 'executor'
  return contextOptions.value.filter((item) => item.kind === preferredKind)
})

const columns = [
  { title: 'Agent ID', dataIndex: 'agent_id', key: 'agent_id' },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '类型', dataIndex: 'agent_type', key: 'agent_type', width: 120 },
  { title: '能力描述', key: 'description' },
  { title: 'Context', dataIndex: 'context_id', key: 'context_id' },
  { title: '操作', key: 'actions', width: 120 },
]

async function create() {
  await agents.createAgent({
    name: form.name,
    agent_type: form.agent_type,
    context_id: form.context_id,
    role_prompt: form.role_prompt,
    metadata: { description: form.description || '' },
  })
  message.success('Agent 已创建')
}

function pickDefaultContext() {
  const target = form.agent_type === 'planner' ? 'default_planner' : 'default_executor'
  const exact = contextOptions.value.find((item) => item.context_id === target)
  const fallback = matchingContexts.value[0]
  form.context_id = exact?.context_id || fallback?.context_id || form.context_id
}

function isProtected(record) {
  return ['default_planner', 'default_executor'].includes(record.agent_id)
}

function confirmDelete(record) {
  Modal.confirm({
    title: '删除 Agent',
    content: `确认删除「${record.name}」及其关联 runs/events 吗？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await agents.deleteAgent(record.agent_id)
      message.success('Agent 已删除')
    },
  })
}

watch(() => form.agent_type, pickDefaultContext)

onMounted(async () => {
  await Promise.all([agents.fetchAgents(), contexts.fetchContexts()])
  pickDefaultContext()
})
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <span class="eyebrow">Agent Factory</span>
        <h1>Agent 管理</h1>
      </div>
      <a-space>
        <a-button @click="agents.fetchAgents">刷新 Agents</a-button>
        <a-button @click="contexts.fetchContexts">刷新 Contexts</a-button>
      </a-space>
    </div>
    <div>

      <a-card class="panel-card" title="Agent 列表" :bordered="false">
        <a-table :columns="columns" :data-source="agents.items" row-key="agent_id" :loading="agents.loading">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'agent_type'">
              <a-tag :color="record.agent_type === 'planner' ? 'purple' : 'blue'">{{ record.agent_type }}</a-tag>
            </template>
            <template v-if="column.key === 'description'">
              {{ record.metadata?.description || '-' }}
            </template>
            <template v-if="column.key === 'context_id'">
              <a-tag>{{ record.context_id }}</a-tag>
            </template>
            <template v-if="column.key === 'actions'">
              <a-button danger size="small" :disabled="isProtected(record)" @click="confirmDelete(record)">
                删除
              </a-button>
            </template>
          </template>
        </a-table>
      </a-card>
    </div>
    <div class="two-column-grid wide-left">
      <a-card class="panel-card" title="创建 Agent" :bordered="false">
        <a-form layout="vertical" >
          <a-form-item label="名称"><a-input v-model:value="form.name" /></a-form-item>
          <a-form-item label="能力描述">
            <a-textarea
              v-model:value="form.description"
              :rows="3"
              placeholder="例如：擅长故事写作、润色、摘要或代码执行"
            />
          </a-form-item>
          <a-form-item label="类型">
            <a-select v-model:value="form.agent_type">
              <a-select-option value="executor">executor</a-select-option>
              <a-select-option value="planner">planner</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="Context">
            <a-select
              v-model:value="form.context_id"
              show-search
              :loading="contexts.loading"
              option-filter-prop="label"
            >
              <a-select-option
                v-for="context in contextOptions"
                :key="context.context_id"
                :value="context.context_id"
                :label="`${context.name} ${context.context_id} ${context.kind}`"
              >
                {{ context.name }} · {{ context.context_id }} · {{ context.kind }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="Role Prompt">
            <a-textarea v-model:value="form.role_prompt" :rows="8" />
          </a-form-item>
          <a-button type="primary" html-type="submit" @click="create">创建</a-button>
        </a-form>
      </a-card>
    </div>
  </section>
</template>
