<script setup>
import { onMounted, ref } from 'vue'
import JsonBlock from '@/components/workflow/JsonBlock.vue'
import { useConversationsStore } from '@/stores/conversations'

const conversations = useConversationsStore()
const title = ref('新会话')

async function create() {
  await conversations.createConversation({ title: title.value, metadata: {} })
}

async function select(record) {
  await conversations.selectConversation(record.conversation_id)
}

const columns = [
  { title: '标题', dataIndex: 'title', key: 'title' },
  { title: 'Conversation ID', dataIndex: 'conversation_id', key: 'conversation_id' },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
]

onMounted(() => conversations.fetchConversations())
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <span class="eyebrow">Conversations</span>
        <h1>会话管理</h1>
      </div>
      <a-space>
        <a-input v-model:value="title" />
        <a-button type="primary" @click="create">新建会话</a-button>
      </a-space>
    </div>

    <div class="two-column-grid wide-left">
      <a-card class="panel-card" title="会话列表" :bordered="false">
        <a-table
          :columns="columns"
          :data-source="conversations.items"
          row-key="conversation_id"
          :loading="conversations.loading"
          :custom-row="record => ({ onClick: () => select(record) })"
        />
      </a-card>
      <a-card class="panel-card" title="会话详情" :bordered="false">
        <a-tabs>
          <a-tab-pane key="messages" tab="Messages">
            <JsonBlock :value="conversations.messages" />
          </a-tab-pane>
          <a-tab-pane key="meta" tab="Current">
            <JsonBlock :value="conversations.current || {}" />
          </a-tab-pane>
        </a-tabs>
      </a-card>
    </div>
  </section>
</template>
