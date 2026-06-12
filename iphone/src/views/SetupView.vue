<script setup>
// 连接服务器页：首启必经。手机访问不到 Mac 的 127.0.0.1，必须可配局域网地址。
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const serverUrl = ref('http://127.0.0.1:8010')
const testing = ref(false)
const errorText = ref('')

onMounted(() => {
  const saved = localStorage.getItem('agent-im-server')
  if (saved) serverUrl.value = saved
})

async function connect() {
  const url = serverUrl.value.trim().replace(/\/+$/, '')
  if (!/^https?:\/\//.test(url)) {
    errorText.value = '地址需要以 http:// 或 https:// 开头'
    return
  }
  testing.value = true
  errorText.value = ''
  try {
    const response = await axios.get(`${url}/health`, { timeout: 4000 })
    if (response.data?.status !== 'ok') throw new Error('bad health')
    localStorage.setItem('agent-im-server', url)
    router.replace({ name: 'login' })
  } catch {
    errorText.value = '连不上这个地址：请确认后端已启动，且手机和 Mac 在同一局域网'
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <div class="setup-page">
    <div class="brand rise-in">
      <div class="brand-mark">A</div>
      <h1>AgentHub</h1>
      <div class="brand-bar"></div>
      <p>连接你的 Agent 服务器</p>
    </div>

    <div class="card setup-form rise-in">
      <div class="field">
        <label>服务器地址</label>
        <input
          v-model="serverUrl"
          type="url"
          placeholder="http://192.168.x.x:8010"
          autocapitalize="off"
          autocorrect="off"
          spellcheck="false"
          @keydown.enter="connect"
        />
      </div>
      <div class="hint-bar">
        <span class="hint-icon">ℹ️</span>
        <p class="hint">
          填 Mac 的局域网地址（如 <code>http://192.168.1.5:8010</code>）；本机调试可用 127.0.0.1。
        </p>
      </div>

      <div v-if="errorText" class="error-bar">{{ errorText }}</div>

      <button class="btn-primary" :disabled="testing" @click="connect">
        {{ testing ? '正在测试连接…' : '测试并连接' }}
      </button>
    </div>

    <p class="footer-note">同一局域网内连接你的 Mac</p>
  </div>
</template>

<style scoped>
.setup-page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: calc(var(--safe-top) + 24px) 26px calc(var(--safe-bottom) + 40px);
  gap: 32px;
}

.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.brand-mark {
  width: 76px;
  height: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 24px;
  background: var(--accent-grad);
  color: #fff;
  font-size: 38px;
  font-weight: 900;
  /* 更深的外投影 + 内高光 */
  box-shadow:
    var(--shadow-accent),
    0 12px 32px rgba(79, 110, 247, 0.40),
    inset 0 1.5px 2px rgba(255, 255, 255, 0.30);
  margin-bottom: 10px;
}

.brand h1 {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.5px;
}

/* 标题下方渐变装饰横条 */
.brand-bar {
  width: 36px;
  height: 3px;
  border-radius: var(--r-pill);
  background: var(--accent-grad);
  opacity: 0.7;
  margin: 2px 0 2px;
}

.brand p {
  color: var(--muted);
  font-size: 14px;
}

/* 表单卡片化：padding 20px */
.setup-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
}

/* ℹ️ 信息条 */
.hint-bar {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--accent-soft);
}

.hint-icon {
  font-size: 14px;
  line-height: 1.6;
  flex: none;
}

.hint {
  font-size: 12.5px;
  color: var(--accent);
  line-height: 1.6;
}

.hint code {
  background: var(--accent-soft-2);
  padding: 1px 5px;
  border-radius: 5px;
  font-size: 11.5px;
}

.error-bar {
  padding: 10px 13px;
  border-radius: var(--r-sm);
  background: var(--red-soft);
  color: var(--red);
  font-size: 13px;
}

/* 底部灰色小注脚 */
.footer-note {
  text-align: center;
  color: var(--muted-2);
  font-size: 12px;
}
</style>
