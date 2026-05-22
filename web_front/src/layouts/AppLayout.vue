<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ApiOutlined,
  AppstoreOutlined,
  CommentOutlined,
  ControlOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  LogoutOutlined,
  RobotOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()

const selectedKeys = computed(() => {
  const path = route.path
  if (path.startsWith('/chat')) return ['chat']
  if (path.startsWith('/tools')) return ['tools']
  if (path.startsWith('/uploads')) return ['uploads']
  if (path.startsWith('/contexts')) return ['contexts']
  if (path.startsWith('/agents')) return ['agents']
  if (path.startsWith('/runs')) return ['runs']
  if (path.startsWith('/conversations')) return ['conversations']
  return ['dashboard']
})

const menuItems = [
  { key: 'dashboard', icon: DashboardOutlined, label: '总览', path: '/dashboard' },
  { key: 'chat', icon: CommentOutlined, label: 'Agent 聊天', path: '/chat' },
  { key: 'runs', icon: DeploymentUnitOutlined, label: '编排运行', path: '/runs' },
  { key: 'conversations', icon: AppstoreOutlined, label: '会话管理', path: '/conversations' },
  { key: 'tools', icon: ToolOutlined, label: '工具库', path: '/tools' },
  { key: 'uploads', icon: ApiOutlined, label: '文件上传', path: '/uploads' },
  { key: 'contexts', icon: ControlOutlined, label: '上下文', path: '/contexts' },
  { key: 'agents', icon: RobotOutlined, label: 'Agents', path: '/agents' },
]

function handleMenu({ key }) {
  const item = menuItems.find((entry) => entry.key === key)
  if (item) router.push(item.path)
}

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  system.fetchHealth()
})
</script>

<template>
  <div class="console-shell">
    <header class="studio-header">
      <div class="brand">
        <div class="brand-mark"><ExperimentOutlined /></div>
        <div>
          <strong>Agent Flow</strong>
          <span>现代编排工作台</span>
        </div>
      </div>

      <nav class="top-nav" aria-label="主导航">
        <button
          v-for="item in menuItems"
          :key="item.key"
          class="nav-pill"
          :class="{ active: selectedKeys.includes(item.key) }"
          @click="router.push(item.path)"
        >
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="header-actions">
        <a-tag :color="system.online ? 'green' : 'red'">
          {{ system.online ? `后端在线 · ${system.health?.mongo}` : '后端未连接' }}
        </a-tag>
        <a-tag v-if="!auth.authApiReady" color="gold">Auth API 未接入</a-tag>
        <a-button size="small" @click="system.fetchHealth">刷新</a-button>
        <a-space>
          <span class="user-name">{{ auth.user?.username || 'local-user' }}</span>
          <a-button type="text" @click="logout">
            <template #icon><LogoutOutlined /></template>
          </a-button>
        </a-space>
      </div>
    </header>

    <main class="console-canvas">
      <!-- <section class="canvas-intro">
        <div>
          <span class="eyebrow">Agent Flow Studio</span>
          <h1>多Agent工作流的可视化操作台</h1>
        </div>
        <p>把后端 API 编排成可观察、可操作、可追踪的前端界面。</p>
      </section> -->

      <RouterView />
    </main>
  </div>
</template>
