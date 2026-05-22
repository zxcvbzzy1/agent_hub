<script setup>
import { h, onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import JsonBlock from '@/components/workflow/JsonBlock.vue'
import { useToolsStore } from '@/stores/tools'
import ToolUploadPanel from './ToolUploadPanel.vue'

const tools = useToolsStore()
const uploadOpen = ref(false)

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
  { title: '领域', dataIndex: 'field', key: 'field', width: 120 },
  { title: '说明', dataIndex: 'description', key: 'description' },
  {
    title: '事件',
    dataIndex: 'events',
    key: 'events',
    width: 280,
    customRender: ({ record }) => h('span', record.events?.length || 0),
  },
  { title: '操作', key: 'actions', width: 130 },
]

function canDelete(record) {
  return record.uploaded === true
}

function confirmDelete(record) {
  Modal.confirm({
    title: '删除工具',
    content: `确认删除上传工具「${record.name}」吗？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await tools.deleteTool(record.name)
      message.success('工具已删除')
    },
  })
}

function handleUploaded() {
  uploadOpen.value = false
}

onMounted(() => tools.fetchTools())
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <span class="eyebrow">Tool Registry</span>
        <h1>工具库</h1>
      </div>
      <a-button type="primary" @click="uploadOpen = true">上传工具</a-button>
    </div>

    <a-card class="panel-card" :bordered="false">
      <a-table
        :columns="columns"
        :data-source="tools.items"
        :loading="tools.loading"
        row-key="name"
        :pagination="{ pageSize: 8 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'field'">
            <a-tag color="blue">{{ record.field || 'unknown' }}</a-tag>
          </template>
          <template v-if="column.key === 'events'">
            <a-space wrap>
              <a-tag v-for="event in record.events || []" :key="event">{{ event.split('.').slice(-1)[0] }}</a-tag>
            </a-space>
          </template>
          <template v-if="column.key === 'actions'">
            <a-button danger size="small" :disabled="!canDelete(record)" @click="confirmDelete(record)">
              删除
            </a-button>
          </template>
        </template>
        <template #expandedRowRender="{ record }">
          <div class="expanded-grid">
            <div>
              <h4>Input Schema</h4>
              <JsonBlock :value="record.input_schema" />
            </div>
            <div>
              <h4>Metadata</h4>
              <JsonBlock :value="record.metadata" />
            </div>
          </div>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="uploadOpen"
      title="上传工具声明与源码"
      width="min(1180px, 96vw)"
      :footer="null"
      destroy-on-close
    >
      <ToolUploadPanel @uploaded="handleUploaded" />
    </a-modal>
  </section>
</template>
