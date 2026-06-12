<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()

const tabs = computed(() => [
  { name: 'conversations', label: '会话', icon: 'chat', badge: chat.totalUnread },
  { name: 'approvals', label: '审批', icon: 'shield', badge: chat.pendingApprovalCount },
  { name: 'settings', label: '我的', icon: 'user', badge: 0 },
])

function go(name) {
  if (route.name !== name) router.replace({ name })
}
</script>

<template>
  <nav class="tabbar">
    <button
      v-for="tab in tabs"
      :key="tab.name"
      class="tab"
      :class="{ 'tab--active': route.name === tab.name }"
      @click="go(tab.name)"
    >
      <span class="tab-icon">
        <!-- 会话 -->
        <svg v-if="tab.icon === 'chat'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
        </svg>
        <!-- 审批 -->
        <svg v-else-if="tab.icon === 'shield'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
        <!-- 我的 -->
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
        <span v-if="tab.badge" class="badge tab-badge">{{ tab.badge > 99 ? '99+' : tab.badge }}</span>
      </span>
      <span class="tab-label">{{ tab.label }}</span>
    </button>
  </nav>
</template>

<style scoped>
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  display: flex;
  height: calc(var(--tabbar-h) + var(--safe-bottom));
  padding-bottom: var(--safe-bottom);
  background: var(--surface-glass);
  backdrop-filter: blur(20px) saturate(1.5);
  -webkit-backdrop-filter: blur(20px) saturate(1.5);
  border-top: 0.5px solid var(--line);
}

.tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  color: var(--muted-2);
  transition: color 0.15s ease;
}

.tab--active {
  color: var(--accent);
}

.tab-icon {
  position: relative;
  display: flex;
}

.tab-icon svg {
  width: 23px;
  height: 23px;
}

.tab-badge {
  position: absolute;
  top: -6px;
  right: -12px;
}

.tab-label {
  font-size: 10.5px;
  font-weight: 700;
}
</style>
