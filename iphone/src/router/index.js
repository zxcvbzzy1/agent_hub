import { createRouter, createWebHashHistory } from 'vue-router'

// 移动端路由：hash 模式（tauri:// 协议无服务端兜底路由）。
// 守卫顺序：未配置服务器 → /setup；未登录 → /login。
const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/setup',
      name: 'setup',
      component: () => import('@/views/SetupView.vue'),
      meta: { public: true, bare: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true, bare: true },
    },
    {
      path: '/',
      name: 'conversations',
      component: () => import('@/views/HomeView.vue'),
      meta: { tab: true },
    },
    // 二级：智能体/群的会话选择页（全屏推入）
    {
      path: '/agent/:agentId',
      name: 'agent-conversations',
      component: () => import('@/views/PickerView.vue'),
      meta: { bare: true },
    },
    {
      path: '/group/:roomId',
      name: 'group-conversations',
      component: () => import('@/views/PickerView.vue'),
      meta: { bare: true },
    },
    {
      path: '/approvals',
      name: 'approvals',
      component: () => import('@/views/ApprovalsView.vue'),
      meta: { tab: true },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { tab: true },
    },
    // 聊天页全屏推入（无 tabbar）：dm 用 conversation_id，group 用 room_id + 可选会话
    {
      path: '/chat/dm/:conversationId',
      name: 'chat-dm',
      component: () => import('@/views/ChatView.vue'),
      meta: { bare: true },
    },
    {
      path: '/chat/group/:roomId/:conversationId?',
      name: 'chat-group',
      component: () => import('@/views/ChatView.vue'),
      meta: { bare: true },
    },
  ],
})

export function getServerUrl() {
  return localStorage.getItem('agent-im-server') || ''
}

function isAuthenticated() {
  try {
    const session = JSON.parse(localStorage.getItem('agent-im-auth') || 'null')
    return Boolean(session?.token)
  } catch {
    return false
  }
}

router.beforeEach((to) => {
  if (!getServerUrl() && to.name !== 'setup') {
    return { name: 'setup' }
  }
  if (!to.meta.public && !isAuthenticated()) {
    return { name: 'login' }
  }
  if (to.meta.public && to.name === 'login' && isAuthenticated()) {
    return { name: 'conversations' }
  }
  return true
})

export default router
