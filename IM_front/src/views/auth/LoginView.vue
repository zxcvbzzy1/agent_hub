<script setup>
import { reactive } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { LockOutlined, UserOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const form = reactive({
  username: 'operator',
  password: 'agent-flow',
})

async function submit() {
  await auth.login(form)
  router.push(route.query.redirect || '/chat')
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-copy">
      <div class="auth-logo">AI</div>
      <h1>Agent IM</h1>
      <p>把 Claude Code、Codex 和你的业务 Agent 放进同一个协作聊天界面。</p>
      <div class="auth-highlights">
        <span>群聊编排</span>
        <span>富消息</span>
        <span>人工确认</span>
      </div>
    </section>
    <a-card class="auth-card" :bordered="false">
      <h2>登录</h2>
      <a-form layout="vertical" :model="form" @finish="submit">
        <a-form-item label="用户名或邮箱" name="username" :rules="[{ required: true, message: '请输入用户名' }]">
          <a-input v-model:value="form.username" size="large">
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>
        <a-form-item label="密码" name="password" :rules="[{ required: true, message: '请输入密码' }]">
          <a-input-password v-model:value="form.password" size="large">
            <template #prefix><LockOutlined /></template>
          </a-input-password>
        </a-form-item>
        <a-button type="primary" html-type="submit" size="large" block :loading="auth.loading">
          进入 Agent IM
        </a-button>
      </a-form>
      <p class="auth-switch">还没有账户？<RouterLink to="/register">注册</RouterLink></p>
    </a-card>
  </main>
</template>
