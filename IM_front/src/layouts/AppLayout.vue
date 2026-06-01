<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { LogoutOutlined, MessageOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useIMStore } from '@/stores/im'

const auth = useAuthStore()
const im = useIMStore()
const router = useRouter()
const displayName = computed(() => auth.user?.display_name || auth.user?.username || 'operator')
const imHeaderCollapsed = ref(false)

function handleImSidebarCollapse(event) {
  imHeaderCollapsed.value = Boolean(event.detail?.collapsed)
}

async function logout() {
  if (im.source) {
    im.source.close()
    im.source = null
  }
  im.$reset()
  await auth.logout()
  router.push('/login')
}

onMounted(() => {
  window.addEventListener('im-sidebar-collapse', handleImSidebarCollapse)
})

onUnmounted(() => {
  window.removeEventListener('im-sidebar-collapse', handleImSidebarCollapse)
})
</script>

<template>
  <div class="app-layout" :class="{ 'im-header-collapsed': imHeaderCollapsed }">
    <header class="app-topbar">
      <div class="topbar-brand">
        <div class="topbar-mark"><MessageOutlined /></div>
        <div>
          <strong>Agent IM</strong>
          <span>协作式多 Agent 工作台</span>
        </div>
      </div>
      <a-space>
        <a-avatar>{{ displayName.slice(0, 1).toUpperCase() }}</a-avatar>
        <span class="topbar-user">{{ displayName }}</span>
        <a-button type="text" @click="logout">
          <template #icon><LogoutOutlined /></template>
          退出
        </a-button>
      </a-space>
    </header>
    <RouterView />
  </div>
</template>
