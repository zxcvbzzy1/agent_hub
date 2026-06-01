<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  BranchesOutlined,
  CodeOutlined,
  CopyOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
  FileTextOutlined,
  GlobalOutlined,
  LinkOutlined,
  MessageOutlined,
  PictureOutlined,
} from '@ant-design/icons-vue'

const props = defineProps({
  artifact: { type: Object, default: () => ({}) },
})

const artifactType = computed(() => (props.artifact?.type || 'message').toLowerCase())
const title = computed(() => props.artifact?.title || defaultTitle(artifactType.value))
const editable = computed(() => Boolean(props.artifact?.editable))

const typeMeta = {
  message: { icon: MessageOutlined, label: '消息' },
  image: { icon: PictureOutlined, label: '图片' },
  diff: { icon: BranchesOutlined, label: 'Diff' },
  document: { icon: FileTextOutlined, label: '文档' },
  web: { icon: GlobalOutlined, label: '网页' },
}

const headerIcon = computed(() => (typeMeta[artifactType.value] || typeMeta.message).icon)
const typeLabel = computed(() => (typeMeta[artifactType.value] || typeMeta.message).label)

// document 本地编辑态（不回写后端）
const docMode = ref('preview')
const docContent = ref('')
watch(
  () => props.artifact,
  (value) => {
    docContent.value = value?.content || ''
    docMode.value = 'preview'
  },
  { immediate: true, deep: true },
)

// web 预览是否展开 iframe
const webExpanded = ref(true)

const diffRows = computed(() => {
  if (artifactType.value !== 'diff') return []
  const before = String(props.artifact?.before ?? '').split('\n')
  const after = String(props.artifact?.after ?? '').split('\n')
  const max = Math.max(before.length, after.length)
  const rows = []
  for (let i = 0; i < max; i += 1) {
    const b = before[i]
    const a = after[i]
    rows.push({
      index: i + 1,
      before: b ?? '',
      after: a ?? '',
      changed: (b ?? '') !== (a ?? ''),
      removed: b !== undefined && b !== a,
      added: a !== undefined && b !== a,
    })
  }
  return rows
})

function defaultTitle(type) {
  return { message: '消息', image: '图片', diff: '代码改动', document: '文档', web: '网页预览' }[type] || '产物'
}

function copy(text) {
  navigator.clipboard?.writeText(text ?? '')
  message.success('已复制')
}

function downloadDocument() {
  const artifact = props.artifact || {}
  const blob = new Blob([docContent.value], { type: artifact.mime_type || 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  const ext = artifact.format || 'txt'
  const base = (artifact.title || 'document').replace(/\s+/g, '_')
  anchor.download = base.includes('.') ? base : `${base}.${ext}`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="artifact-card" :class="`artifact-${artifactType}`">
    <div class="artifact-head">
      <component :is="headerIcon" class="artifact-head-icon" />
      <span class="artifact-title">{{ title }}</span>
      <a-tag size="small" class="artifact-type-tag">{{ typeLabel }}</a-tag>
      <span class="artifact-head-spacer"></span>

      <template v-if="artifactType === 'document'">
        <a-tag v-if="artifact.format" size="small" color="blue">{{ artifact.format }}</a-tag>
        <a-button v-if="editable" type="text" size="small" @click="docMode = docMode === 'edit' ? 'preview' : 'edit'">
          <template #icon><EditOutlined v-if="docMode === 'preview'" /><EyeOutlined v-else /></template>
          {{ docMode === 'preview' ? '编辑' : '预览' }}
        </a-button>
        <a-button type="text" size="small" @click="copy(docContent)">
          <template #icon><CopyOutlined /></template>
        </a-button>
        <a-button type="text" size="small" @click="downloadDocument">
          <template #icon><DownloadOutlined /></template>
        </a-button>
      </template>

      <template v-else-if="artifactType === 'diff'">
        <a-tag v-if="artifact.file_path" size="small">{{ artifact.file_path }}</a-tag>
        <a-button type="text" size="small" @click="copy(artifact.after)">
          <template #icon><CopyOutlined /></template>
        </a-button>
      </template>

      <template v-else-if="artifactType === 'web'">
        <a-button type="text" size="small" @click="webExpanded = !webExpanded">
          <template #icon><EyeOutlined /></template>
          {{ webExpanded ? '收起' : '展开' }}
        </a-button>
        <a v-if="artifact.url" :href="artifact.url" target="_blank" rel="noopener" class="artifact-open-link">
          <LinkOutlined /> 打开
        </a>
      </template>

      <template v-else-if="artifactType === 'message'">
        <a-button type="text" size="small" @click="copy(artifact.content)">
          <template #icon><CopyOutlined /></template>
        </a-button>
      </template>
    </div>

    <!-- message -->
    <div v-if="artifactType === 'message'" class="artifact-body artifact-message-body">
      <p v-if="artifact.content" class="artifact-text">{{ artifact.content }}</p>
      <a-empty v-else description="空消息" :image-style="{ height: '40px' }" />
    </div>

    <!-- image -->
    <div v-else-if="artifactType === 'image'" class="artifact-body artifact-image-body">
      <img v-if="artifact.url" :src="artifact.url" :alt="artifact.alt || title" class="artifact-image" />
      <a-empty v-else description="缺少图片地址" :image-style="{ height: '40px' }" />
      <small v-if="artifact.alt" class="artifact-caption">{{ artifact.alt }}</small>
    </div>

    <!-- diff -->
    <div v-else-if="artifactType === 'diff'" class="artifact-body artifact-diff-body">
      <table class="artifact-diff-table">
        <tbody>
          <tr v-for="row in diffRows" :key="row.index" :class="{ changed: row.changed }">
            <td class="diff-gutter">{{ row.index }}</td>
            <td class="diff-before" :class="{ removed: row.changed && row.before }">
              <span class="diff-sign">{{ row.changed && row.before ? '-' : '' }}</span>{{ row.before }}
            </td>
            <td class="diff-after" :class="{ added: row.changed && row.after }">
              <span class="diff-sign">{{ row.changed && row.after ? '+' : '' }}</span>{{ row.after }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- document -->
    <div v-else-if="artifactType === 'document'" class="artifact-body artifact-document-body">
      <a-textarea
        v-if="docMode === 'edit'"
        v-model:value="docContent"
        :auto-size="{ minRows: 4, maxRows: 18 }"
        class="artifact-doc-editor"
      />
      <pre v-else class="artifact-doc-preview"><code>{{ docContent }}</code></pre>
    </div>

    <!-- web -->
    <div v-else-if="artifactType === 'web'" class="artifact-body artifact-web-body">
      <div class="artifact-web-bar">
        <GlobalOutlined />
        <span class="artifact-web-title">{{ artifact.preview_title || artifact.url || title }}</span>
      </div>
      <iframe
        v-if="webExpanded && artifact.html"
        class="artifact-web-frame"
        :srcdoc="artifact.html"
        sandbox="allow-scripts allow-popups allow-forms"
        referrerpolicy="no-referrer"
      ></iframe>
      <iframe
        v-else-if="webExpanded && artifact.url"
        class="artifact-web-frame"
        :src="artifact.url"
        sandbox="allow-scripts allow-popups allow-forms allow-same-origin"
        referrerpolicy="no-referrer"
      ></iframe>
      <a v-else-if="!webExpanded && artifact.url" :href="artifact.url" target="_blank" rel="noopener" class="artifact-web-link">
        {{ artifact.url }}
      </a>
      <a-empty v-else-if="!artifact.html && !artifact.url" description="缺少网页内容" :image-style="{ height: '40px' }" />
    </div>

    <!-- fallback -->
    <div v-else class="artifact-body">
      <a-tag>
        <CodeOutlined />
        {{ artifactType }}
      </a-tag>
    </div>
  </div>
</template>

<style scoped>
.artifact-card {
  border: 1px solid var(--ant-color-border, #e5e7eb);
  border-radius: 12px;
  overflow: hidden;
  background: var(--ant-color-bg-container, #fff);
  margin-top: 8px;
}
.artifact-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.025);
  border-bottom: 1px solid var(--ant-color-border, #eef0f3);
  font-size: 13px;
}
.artifact-head-icon {
  color: #6b7280;
}
.artifact-title {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}
.artifact-type-tag {
  margin: 0;
}
.artifact-head-spacer {
  flex: 1;
}
.artifact-open-link,
.artifact-web-link {
  color: #2563eb;
  font-size: 12px;
  white-space: nowrap;
}
.artifact-body {
  padding: 12px;
}
.artifact-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
.artifact-image {
  max-width: 100%;
  border-radius: 8px;
  display: block;
}
.artifact-caption {
  display: block;
  margin-top: 6px;
  color: #6b7280;
}
.artifact-diff-body {
  padding: 0;
  overflow-x: auto;
}
.artifact-diff-table {
  width: 100%;
  border-collapse: collapse;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
}
.artifact-diff-table td {
  padding: 0 8px;
  vertical-align: top;
  white-space: pre-wrap;
  word-break: break-word;
}
.diff-gutter {
  width: 36px;
  text-align: right;
  color: #9ca3af;
  user-select: none;
  background: rgba(0, 0, 0, 0.02);
}
.diff-before,
.diff-after {
  width: 50%;
}
.diff-sign {
  display: inline-block;
  width: 12px;
  color: inherit;
  opacity: 0.7;
}
.diff-before.removed {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}
.diff-after.added {
  background: rgba(34, 197, 94, 0.14);
  color: #15803d;
}
.artifact-doc-editor :deep(textarea),
.artifact-doc-preview {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12.5px;
}
.artifact-doc-preview {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 420px;
  overflow: auto;
}
.artifact-web-body {
  padding: 0;
}
.artifact-web-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  color: #6b7280;
  border-bottom: 1px solid var(--ant-color-border, #eef0f3);
}
.artifact-web-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.artifact-web-frame {
  width: 100%;
  height: 360px;
  border: 0;
  display: block;
  background: #fff;
}
.artifact-web-link {
  display: block;
  padding: 12px;
  word-break: break-all;
}
</style>
