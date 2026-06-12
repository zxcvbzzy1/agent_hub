<script setup>
import { reactive } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({
  username: 'operator',
  display_name: 'Operator',
  email: 'operator@example.com',
  password: 'agent-flow',
})

async function submit() {
  await auth.register(form)
  router.push('/chat')
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-copy">
      <div class="auth-logo">IM</div>
      <h1>创建工作台账户</h1>
      <p>账户会存入 IM 后端数据库，并用于创建房间、发送消息和确认任务。</p>
      <div class="auth-highlights">
        <span>数据库 session</span>
        <span>Bearer Token</span>
        <span>本地可用</span>
      </div>
    </section>
    <a-card class="auth-card" :bordered="false">
      <h2>注册</h2>
      <a-form layout="vertical" :model="form" @finish="submit">
        <a-form-item label="用户名" name="username" :rules="[{ required: true, message: '请输入用户名' }]">
          <a-input v-model:value="form.username" size="large">
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>
        <a-form-item label="显示名称">
          <a-input v-model:value="form.display_name" size="large">
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>
        <a-form-item label="邮箱" name="email" :rules="[{ required: true, message: '请输入邮箱' }]">
          <a-input v-model:value="form.email" size="large">
            <template #prefix><MailOutlined /></template>
          </a-input>
        </a-form-item>
        <a-form-item label="密码" name="password" :rules="[{ required: true, message: '请输入密码' }]">
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
