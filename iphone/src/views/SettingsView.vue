<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getApiBaseUrl } from '@/api/http'

const router = useRouter()
const auth = useAuthStore()

const displayName = computed(() => auth.user?.display_name || auth.user?.username || 'operator')
const serverUrl = computed(() => getApiBaseUrl() || '未配置')

async function logout() {
  await auth.logout()
  router.replace({ name: 'login' })
}

function editServer() {
  router.push({ name: 'setup' })
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">我的</h1>

    <div class="card user-card rise-in">
      <div class="avatar user-avatar hue-0">
        <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" alt="" />
        <template v-else>{{ displayName.slice(0, 1).toUpperCase() }}</template>
      </div>
      <div class="user-info">
        <strong>{{ displayName }}</strong>
        <span>@{{ auth.user?.username || '—' }}</span>
      </div>
      <span class="user-chevron">›</span>
    </div>

    <div class="card setting-card rise-in">
      <div class="setting-row">
        <div class="setting-text">
          <strong>服务器</strong>
          <span>{{ serverUrl }}</span>
        </div>
        <button class="setting-action" @click="editServer">修改</button>
      </div>
      <div class="setting-divider"></div>
      <div class="setting-row">
        <div class="setting-text">
          <strong>关于</strong>
        </div>
        <span class="setting-about-ver">v0.1.0</span>
      </div>
    </div>

    <button class="btn-danger logout-btn rise-in" @click="logout">退出登录</button>

    <p class="version">AgentHub Mobile v0.1.0</p>
  </div>
</template>

<style scoped>
.user-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px;
  margin-bottom: 14px;
}

/* 64px 头像 + hue-0 渐变 + 白色 2px ring + 阴影 */
.user-avatar {
  width: 64px;
  height: 64px;
  font-size: 26px;
  box-shadow:
    0 0 0 2.5px #fff,
    0 0 0 4px rgba(99, 102, 241, 0.20),
    0 4px 12px rgba(99, 102, 241, 0.24);
  flex: none;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.user-info strong {
  font-size: 18px;
  letter-spacing: -0.2px;
}

.user-info span {
  color: var(--muted);
  font-size: 13px;
}

/* 用户卡右侧灰色 chevron */
.user-chevron {
  font-size: 20px;
  color: var(--muted-2);
  flex: none;
  line-height: 1;
}

.setting-card {
  margin-bottom: 24px;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 18px;
}

/* 行间 0.5px 分隔线 */
.setting-divider {
  height: 0.5px;
  background: var(--line);
  margin: 0 18px;
}

.setting-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.setting-text strong {
  font-size: 14.5px;
}

.setting-text span {
  color: var(--muted);
  font-size: 12.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.setting-action {
  flex: none;
  padding: 6px 14px;
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 13px;
  font-weight: 800;
}

/* 「关于」行右侧灰色版本文字 */
.setting-about-ver {
  flex: none;
  color: var(--muted-2);
  font-size: 13px;
}

/* 退出按钮上方 24px */
.logout-btn {
  width: 100%;
  height: 48px;
  margin-top: 24px;
}

.version {
  text-align: center;
  color: var(--muted-2);
  font-size: 12px;
  margin-top: 26px;
}
</style>
