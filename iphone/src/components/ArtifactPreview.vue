<script setup>
// 全屏产物预览：document/message(markdown)、image、diff、web(iframe)、video。
// 移动端不做编辑/落盘，纯预览 + 复制。
import { computed, ref } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { getApiBaseUrl } from '@/api/http'

const props = defineProps({
  artifact: { type: Object, required: true },
})
const emit = defineEmits(['close'])

const copied = ref(false)
const diffSide = ref('after')

const type = computed(() => (props.artifact?.type || 'message').toLowerCase())

const title = computed(
  () => props.artifact?.title || props.artifact?.file_path || TYPE_LABEL[type.value] || '产物',
)

const TYPE_LABEL = {
  message: '消息',
  document: '文档',
  image: '图片',
  diff: '代码改动',
  web: '网页',
  video: '视频',
  deploy: '部署',
}

function absoluteUrl(url) {
  if (!url) return ''
  if (/^(https?:)?\/\//.test(url) || url.startsWith('data:') || url.startsWith('blob:')) return url
  return `${getApiBaseUrl()}${url.startsWith('/') ? '' : '/'}${url}`
}

const imageUrl = computed(() => absoluteUrl(props.artifact?.url))
const videoUrl = computed(() => absoluteUrl(props.artifact?.url))

const markdownHtml = computed(() => {
  const content = props.artifact?.content || ''
  return renderMarkdown(content)
})

const diffText = computed(() => {
  if (diffSide.value === 'before') return props.artifact?.before ?? ''
  return props.artifact?.after ?? props.artifact?.content ?? ''
})

const copySource = computed(() => {
  if (type.value === 'diff') return diffText.value
  if (type.value === 'web') return props.artifact?.html || props.artifact?.url || ''
  return props.artifact?.content || props.artifact?.url || ''
})

async function copy() {
  try {
    await navigator.clipboard?.writeText(copySource.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1400)
  } catch {
    // 移动 webview 剪贴板不可用时静默
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="preview-mask" @click.self="emit('close')">
      <div class="preview-sheet rise-in">
        <header class="preview-head">
          <div class="preview-title">
            <span class="preview-type">{{ TYPE_LABEL[type] || '产物' }}</span>
            <strong>{{ title }}</strong>
          </div>
          <div class="preview-actions">
            <button v-if="copySource" class="icon-btn" :class="{ 'icon-btn--ok': copied }" @click="copy">
              <svg v-if="!copied" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </button>
            <button class="icon-btn" @click="emit('close')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </header>

        <div class="preview-body">
          <!-- 文档 / 消息：markdown 渲染 -->
          <div v-if="type === 'document' || type === 'message'" class="md-body preview-md" v-html="markdownHtml"></div>

          <!-- 图片 -->
          <div v-else-if="type === 'image'" class="preview-center">
            <img v-if="imageUrl" :src="imageUrl" :alt="title" class="preview-image" />
            <div v-else class="empty">图片地址缺失</div>
          </div>

          <!-- 视频 -->
          <div v-else-if="type === 'video'" class="preview-center">
            <video v-if="videoUrl" :src="videoUrl" controls playsinline class="preview-video"></video>
            <div v-else class="empty">视频地址缺失</div>
          </div>

          <!-- Diff：before/after 切换 -->
          <template v-else-if="type === 'diff'">
            <div class="diff-toggle">
              <button :class="{ on: diffSide === 'before' }" @click="diffSide = 'before'">修改前</button>
              <button :class="{ on: diffSide === 'after' }" @click="diffSide = 'after'">修改后</button>
            </div>
            <pre class="preview-code">{{ diffText || '（空）' }}</pre>
          </template>

          <!-- 网页：srcdoc 沙箱 iframe -->
          <template v-else-if="type === 'web'">
            <iframe
              v-if="artifact.html"
              class="preview-frame"
              sandbox="allow-scripts"
              :srcdoc="artifact.html"
            ></iframe>
            <iframe v-else-if="artifact.url" class="preview-frame" sandbox="allow-scripts" :src="absoluteUrl(artifact.url)"></iframe>
            <div v-else class="empty">没有可预览的网页内容</div>
          </template>

          <!-- 其它（deploy 等）：移动端只读提示 -->
          <div v-else class="empty">
            <span class="empty-icon">🖥️</span>
            <span>该类型产物（{{ artifact.type }}）请在桌面端查看与操作</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.preview-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: flex-end;
}

.preview-sheet {
  width: 100%;
  height: calc(100% - var(--safe-top) - 28px);
  background: var(--bg);
  border-radius: 24px 24px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 16px 12px;
  background: var(--surface-glass);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 0.5px solid var(--line);
}

.preview-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.preview-title strong {
  font-size: 15.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-type {
  flex: none;
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11.5px;
  font-weight: 800;
}

.preview-actions {
  display: flex;
  gap: 8px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-pill);
  background: rgba(15, 23, 42, 0.05);
  color: var(--ink-2);
}

.icon-btn svg {
  width: 17px;
  height: 17px;
}

.icon-btn--ok {
  background: var(--green-soft);
  color: var(--green);
}

.preview-body {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 16px;
}

.preview-md {
  background: var(--surface);
  border-radius: var(--r-md);
  padding: 16px;
  box-shadow: var(--shadow-card);
  font-size: 14.5px;
  word-break: break-word;
}

.preview-center {
  display: flex;
  justify-content: center;
}

.preview-image {
  max-width: 100%;
  border-radius: var(--r-md);
  box-shadow: var(--shadow-card);
}

.preview-video {
  width: 100%;
  border-radius: var(--r-md);
  background: #000;
}

.diff-toggle {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  margin-bottom: 10px;
  border-radius: var(--r-pill);
  background: rgba(15, 23, 42, 0.06);
}

.diff-toggle button {
  padding: 6px 16px;
  border-radius: var(--r-pill);
  font-size: 13px;
  font-weight: 700;
  color: var(--muted);
}

.diff-toggle button.on {
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-card);
}

.preview-code {
  background: #0d1422;
  color: #e2ecff;
  border-radius: var(--r-md);
  padding: 14px;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.preview-frame {
  width: 100%;
  height: 100%;
  min-height: 420px;
  border: none;
  border-radius: var(--r-md);
  background: #fff;
  box-shadow: var(--shadow-card);
}
</style>
