<script setup>
import { reactive } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import { LockOutlined, UserOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const form = reactive({
  username: 'operator',
  password: 'agent-flow',
})

async function submit() {
  await auth.login(form)
  console.log('登录信息', form)
  router.push(route.query.redirect || '/dashboard')
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-visual">
      <div class="auth-mark">AF</div>
      <h1>Agent Flow Control Plane</h1>
      <p>面向工具、上下文、Agent 编排和事件流观察的一体化操作台。</p>
    </section>
    <a-card class="auth-card" :bordered="false">
      <h2>登录</h2>
      <a-alert
        v-if="!auth.authApiReady"
        class="mb-16"
        type="warning"
        show-icon
        message="Auth API 未接入，当前使用本地临时登录态。"
      />
      <a-form  :model="form" layout="vertical" @finish="submit">
        <a-form-item label="用户名">
          <a-input v-model:value="form.username" size="large">
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="form.password" size="large">
            <template #prefix><LockOutlined /></template>
          </a-input-password>
        </a-form-item>
        <a-button type="primary" html-type="submit" size="large" block :loading="auth.loading">
          进入控制台
        </a-button>
      </a-form>
      <p class="auth-switch">还没有账户？<RouterLink to="/register">注册</RouterLink></p>
    </a-card>
  </main>
</template>

