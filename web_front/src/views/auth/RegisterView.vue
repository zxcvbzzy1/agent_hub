<script setup>
import { reactive } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { MailOutlined, LockOutlined, UserOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({
  username: 'new-operator',
  email: 'operator@example.com',
  password: 'agent-flow',
})

async function submit() {
  await auth.register(form)
  router.push('/dashboard')
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-visual">
      <div class="auth-mark">AF</div>
      <h1>注册操作员</h1>
      <p>后端认证接口尚未提供，页面会预留 API 调用并降级到本地 session。</p>
    </section>
    <a-card class="auth-card" :bordered="false">
      <h2>注册</h2>
      <a-form layout="vertical" @finish="submit">
        <a-form-item label="用户名">
          <a-input v-model:value="form.username" size="large">
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>
        <a-form-item label="邮箱">
          <a-input v-model:value="form.email" size="large">
            <template #prefix><MailOutlined /></template>
          </a-input>
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="form.password" size="large">
            <template #prefix><LockOutlined /></template>
          </a-input-password>
        </a-form-item>
        <a-button type="primary" html-type="submit" size="large" block :loading="auth.loading">
          创建并进入
        </a-button>
      </a-form>
      <p class="auth-switch">已有账户？<RouterLink to="/login">登录</RouterLink></p>
    </a-card>
  </main>
</template>

