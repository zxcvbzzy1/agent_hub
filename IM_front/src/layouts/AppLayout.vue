<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { LogoutOutlined, MessageOutlined, BookOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useIMStore } from '@/stores/im'

const auth = useAuthStore()
const im = useIMStore()
const router = useRouter()
const route = useRoute()
const displayName = computed(() => auth.user?.display_name || auth.user?.username || 'operator')
const imHeaderCollapsed = ref(false)

const activeNav = computed(() => route.name)

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
      <!-- left: brand -->
      <div class="topbar-brand">
        <div class="topbar-mark"><MessageOutlined /></div>
        <div>
          <strong>Agent IM</strong>
          <span>协作式多 Agent 工作台</span>
        </div>
      </div>

      <!-- center: capsule segmented nav -->
      <nav class="topbar-nav" aria-label="主导航">
        <div class="topbar-pill">
          <RouterLink
            :to="{ name: 'chat' }"
            class="topbar-pill-seg"
            :class="{ 'topbar-pill-seg--active': activeNav === 'chat' }"
          >
            <MessageOutlined class="pill-icon" />
            聊天
          </RouterLink>
          <RouterLink
            :to="{ name: 'skills' }"
            class="topbar-pill-seg"
            :class="{ 'topbar-pill-seg--active': activeNav === 'skills' }"
          >
            <BookOutlined class="pill-icon" />
            技能库
          </RouterLink>
        </div>
      </nav>

      <!-- right: user area -->
      <div class="topbar-user-area">
        <a-space>
          <a-avatar>{{ displayName.slice(0, 1).toUpperCase() }}</a-avatar>
          <span class="topbar-user">{{ displayName }}</span>
          <a-button type="text" @click="logout">
            <template #icon><LogoutOutlined /></template>
            退出
          </a-button>
        </a-space>
      </div>
    </header>
    <RouterView />
  </div>
</template>

<style scoped>
/* Three-section topbar: brand | nav (centered) | user-area */
.app-topbar {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
}

.topbar-user-area {
  display: flex;
  justify-content: flex-end;
}

/* ── capsule pill ── */
.topbar-nav {
  display: flex;
  align-items: center;
  justify-content: center;
}

.topbar-pill {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.52);
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 999px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.86),
    0 8px 22px rgba(27, 39, 66, 0.08);
  backdrop-filter: blur(12px);
}

.topbar-pill-seg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--muted);
  text-decoration: none;
  transition:
    color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.14s ease;
  white-space: nowrap;
  user-select: none;
}

.topbar-pill-seg:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.62);
}

.topbar-pill-seg--active {
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-2) 60%, var(--accent-5));
  box-shadow:
    0 4px 14px rgba(53, 120, 255, 0.30),
    inset 0 1px 0 rgba(255, 255, 255, 0.22);
  transform: translateY(-0.5px);
}

.topbar-pill-seg--active:hover {
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-2) 60%, var(--accent-5));
}

.pill-icon {
  font-size: 13px;
}

/* ── responsive: stack vertically on narrow screens ── */
@media (max-width: 760px) {
  .app-topbar {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    height: auto;
    gap: 10px;
    padding: 12px 14px;
  }

  .topbar-nav {
    align-self: center;
  }

  .topbar-user-area {
    align-self: flex-end;
  }
}
</style>
