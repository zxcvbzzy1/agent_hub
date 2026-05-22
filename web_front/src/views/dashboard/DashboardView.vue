<script setup>
import { computed, onMounted } from 'vue'
import {
  ApiOutlined,
  CommentOutlined,
  DeploymentUnitOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'
import { useAgentsStore } from '@/stores/agents'
import { useConversationsStore } from '@/stores/conversations'
import { useSystemStore } from '@/stores/system'
import { useToolsStore } from '@/stores/tools'

const system = useSystemStore()
const tools = useToolsStore()
const agents = useAgentsStore()
const conversations = useConversationsStore()
const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const stats = computed(() => [
  { title: '工具', value: tools.items.length, icon: ApiOutlined, color: 'blue' },
  { title: 'Agents', value: agents.items.length, icon: RobotOutlined, color: 'purple' },
  { title: '会话', value: conversations.items.length, icon: CommentOutlined, color: 'green' },
  { title: '后端', value: system.online ? 'Online' : 'Offline', icon: DeploymentUnitOutlined, color: system.online ? 'green' : 'red' },
])

onMounted(() => {
  system.fetchHealth()
  tools.fetchTools().catch(() => {})
  agents.fetchAgents().catch(() => {})
  conversations.fetchConversations().catch(() => {})
})
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <span class="eyebrow">Control Overview</span>
        <h1>Agent Flow 操作总览</h1>
      </div>
      <a-button type="primary" @click="system.fetchHealth">检查后端</a-button>
    </div>

    <div class="stat-grid">
      <a-card v-for="item in stats" :key="item.title" class="metric-card" :bordered="false">
        <div class="metric-icon" :class="`metric-${item.color}`">
          <component :is="item.icon" />
        </div>
        <a-statistic :title="item.title" :value="item.value" />
      </a-card>
    </div>

    <div class="two-column-grid">
      <a-card class="panel-card" title="后端连接" :bordered="false">
        <a-descriptions :column="1" size="small">
          <a-descriptions-item label="Base URL">
            {{ apiBase }}
          </a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="system.online ? 'green' : 'red'">{{ system.online ? 'ok' : 'disconnected' }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="存储">{{ system.health?.mongo || '-' }}</a-descriptions-item>
        </a-descriptions>
      </a-card>

      <a-card class="panel-card" title="常用入口" :bordered="false">
        <div class="quick-actions">
          <RouterLink to="/chat"><a-button type="primary">开始聊天</a-button></RouterLink>
          <RouterLink to="/runs"><a-button>创建 Run</a-button></RouterLink>
          <RouterLink to="/tools"><a-button>上传工具</a-button></RouterLink>
          <RouterLink to="/agents"><a-button>管理 Agent</a-button></RouterLink>
        </div>
      </a-card>
    </div>
  </section>
</template>
