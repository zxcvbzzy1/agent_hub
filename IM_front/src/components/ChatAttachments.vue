<script setup>
import { ref, watch } from 'vue'
import { CloudUploadOutlined, FileTextOutlined, CloseOutlined } from '@ant-design/icons-vue'
import { filesApi, fileSize } from '@/api/files'

const props = defineProps({ items: { type: Array, default: () => [] }, disabled: Boolean, targetKey: String })
const emit = defineEmits(['upload', 'reuse', 'remove', 'retry'])
const input = ref(null)
const open = ref(false)
const loading = ref(false)
const files = ref([])
const cursor = ref('')
const hasMore = ref(false)
watch(() => props.targetKey, () => { open.value = false })
async function load(reset = false) {
  loading.value = true
  try {
    const result = await filesApi.list(reset ? '' : cursor.value)
    files.value = reset ? result.items : [...files.value, ...result.items]
    cursor.value = result.next_cursor
    hasMore.value = result.has_more
  } catch { /* HTTP interceptor displays the error. */ } finally { loading.value = false }
}
function pick() { open.value = true; load(true) }
function selected(event) {
  emit('upload', Array.from(event.target.files || []))
  event.target.value = ''
}
</script>

<template>
  <div class="chat-attachments">
    <a-space wrap>
      <input ref="input" type="file" multiple hidden @change="selected" />
      <a-button :disabled="disabled" @click="input.click()"><CloudUploadOutlined /> 上传文件</a-button>
      <a-button :disabled="disabled" @click="pick"><FileTextOutlined /> 选择已上传文件</a-button>
      <span class="attachment-limit">最多 10 个，每个 20 MiB</span>
    </a-space>
    <div class="big-box">
      <div v-for="item in items" :key="item.key" class="draft-file">
        <FileTextOutlined />
        <span class="file-name" :title="item.name">{{ item.name }}</span>
        <small>{{ fileSize(item.size) }}</small>
        <span v-if="item.state === 'uploading'">上传中 {{ item.progress }}%</span>
        <span v-else-if="item.state === 'failed'" class="file-error">上传失败</span>
        <span v-else-if="item.state === 'deleted'" class="file-error">文件已删除</span>
        <a-button v-if="item.state === 'failed' && item.raw" size="small" :disabled="disabled" @click="emit('retry', item)">重试</a-button>
        <a-button type="text" size="small" aria-label="移除附件" :disabled="disabled" @click="emit('remove', item)"><CloseOutlined /></a-button>
      </div>
    </div>
      
    <a-modal v-model:open="open" title="我的已上传文件" :footer="null">
      <a-spin :spinning="loading">
        <a-empty v-if="!files.length && !loading" description="暂无已发送的文件" />
        <div v-for="file in files" :key="file.file_id" class="draft-file">
          <span class="file-name">{{ file.original_name }}</span>
          <small>{{ fileSize(file.size) }}</small>
          <a-button size="small" :disabled="disabled || items.some(i => i.file?.file_id === file.file_id)" @click="emit('reuse', file)">添加</a-button>
        </div>
        <a-button v-if="hasMore" block :loading="loading" @click="load()">加载更多</a-button>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.chat-attachments { margin: 8px 0 12px; }
.attachment-limit { font-size: 12px; color: #888; }
.draft-file { 
  display: flex; 
  align-items: center; 
  gap: 8px; 
  padding: 8px 10px; 
  margin-top: 6px; 
  border: 1px solid var(--border-color, #e8e8e8); 
  border-radius: 8px; 

}
.big-box { 
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  max-height: 200px; 
  overflow-y: auto; 
  margin-top: 8px; 
}
.file-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-error { color: #c33; }
</style>
