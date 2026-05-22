import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/auth/RegisterView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/dashboard/DashboardView.vue') },
      { path: 'chat', name: 'chat', component: () => import('@/views/chat/ChatView.vue') },
      { path: 'tools', name: 'tools', component: () => import('@/views/tools/ToolsView.vue') },
      { path: 'tools/upload', redirect: '/tools' },
      { path: 'uploads', name: 'uploads', component: () => import('@/views/uploads/UploadsView.vue') },
      { path: 'contexts', name: 'contexts', component: () => import('@/views/contexts/ContextsView.vue') },
      { path: 'agents', name: 'agents', component: () => import('@/views/agents/AgentsView.vue') },
      { path: 'runs', name: 'runs', component: () => import('@/views/runs/RunsView.vue') },
      { path: 'conversations', name: 'conversations', component: () => import('@/views/conversations/ConversationsView.vue') },
    ],
  },
  {
    path: '/runs/:runId/events',
    name: 'run-events',
    component: () => import('@/views/runs/RunEventsView.vue'),
  },
  {
    path: '/executor-frame/:runId/:executorId?',
    name: 'executor-frame',
    component: () => import('@/views/runs/ExecutorFrameView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.public && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
