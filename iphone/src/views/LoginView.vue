<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getApiBaseUrl } from '@/api/http'

const router = useRouter()
const auth = useAuthStore()

const mode = ref('login') // 'login' | 'register'
const username = ref('')
const password = ref('')
const email = ref('')
const displayName = ref('')
const errorText = ref('')

const isLogin = computed(() => mode.value === 'login')

// 仅展示用：读取已保存的服务器地址
const serverLabel = computed(() => getApiBaseUrl() || '')

function switchMode() {
  mode.value = isLogin.value ? 'register' : 'login'
  errorText.value = ''
}

async function submit() {
  if (!username.value.trim() || !password.value) {
    errorText.value = '请输入用户名和密码'
    return
  }
  errorText.value = ''
  try {
    if (isLogin.value) {
      await auth.login({ username: username.value.trim(), password: password.value })
    } else {
      await auth.register({
        username: username.value.trim(),
        password: password.value,
        email: email.value.trim(),
        display_name: displayName.value.trim() || username.value.trim(),
      })
    }
    router.replace('/')
  } catch (error) {
    errorText.value = error?.response?.data?.detail || '操作失败，请重试'
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-head rise-in">
      <div class="brand-mark">A</div>
      <h1>{{ isLogin ? '欢迎回来' : '创建账号' }}</h1>
      <p>{{ isLogin ? '登录后继续与你的智能体协作' : '注册一个 AgentHub 账号' }}</p>
    </div>

    <Transition name="form-fade" mode="out-in">
      <form :key="mode" class="card login-form rise-in" @submit.prevent="submit">
        <div class="field focus-label">
          <label>用户名</label>
          <input v-model="username" autocapitalize="off" autocorrect="off" placeholder="username" />
        </div>
        <div v-if="!isLogin" class="field focus-label">
          <label>邮箱</label>
          <input v-model="email" type="email" autocapitalize="off" placeholder="you@example.com" />
        </div>
        <div v-if="!isLogin" class="field focus-label">
          <label>显示名</label>
          <input v-model="displayName" placeholder="昵称（可选）" />
        </div>
        <div class="field focus-label">
          <label>密码</label>
          <input v-model="password" type="password" placeholder="••••••••" />
        </div>

        <div v-if="errorText" class="error-bar">{{ errorText }}</div>

        <button type="submit" class="btn-primary" :disabled="auth.loading">
          {{ auth.loading ? '请稍候…' : isLogin ? '登录' : '注册并登录' }}
        </button>

        <p v-if="serverLabel" class="server-hint">连接到 {{ serverLabel }}</p>
      </form>
    </Transition>

    <p class="switch-line">
      {{ isLogin ? '还没有账号？' : '已有账号？' }}
      <button class="switch-btn" @click="switchMode">{{ isLogin ? '注册' : '去登录' }}</button>
    </p>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: calc(var(--safe-top) + 24px) 26px calc(var(--safe-bottom) + 36px);
  gap: 22px;
}

.login-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}

.brand-mark {
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 20px;
  background: var(--accent-grad);
  color: #fff;
  font-size: 30px;
  font-weight: 900;
  box-shadow: var(--shadow-accent);
  margin-bottom: 10px;
}

.login-head h1 {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.login-head p {
  color: var(--muted);
  font-size: 13.5px;
}

/* 表单卡片化：padding 20px */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
}

/* 聚焦时 label 变 accent 色 */
.focus-label:focus-within label {
  color: var(--accent);
  transition: color 0.15s ease;
}

.error-bar {
  padding: 10px 13px;
  border-radius: var(--r-sm);
  background: var(--red-soft);
  color: var(--red);
  font-size: 13px;
}

/* 主按钮下方服务器地址小字 */
.server-hint {
  text-align: center;
  color: var(--muted-2);
  font-size: 12px;
  margin-top: -2px;
}

.switch-line {
  text-align: center;
  color: var(--muted);
  font-size: 13.5px;
}

.switch-btn {
  color: var(--accent);
  font-weight: 800;
  font-size: 13.5px;
}

/* 登录/注册切换 fade 过渡 */
.form-fade-enter-active,
.form-fade-leave-active {
  transition: opacity 0.15s ease;
}
.form-fade-enter-from,
.form-fade-leave-to {
  opacity: 0;
}
</style>
