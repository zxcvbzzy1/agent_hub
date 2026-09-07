<script setup>
import { computed, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { DownloadOutlined, DeleteOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { filesApi, fileSize } from '@/api/files'
import { useAuthStore } from '@/stores/auth'
const props = defineProps({ part: { type: Object, required: true } })
const emit = defineEmits(['deleted'])
const auth = useAuthStore()
const downloading = ref(false)
const deleted = ref(false)
const unavailable = computed(() => deleted.value || ['delete', 'deleting'].includes(props.part.metadata?.file_status))
async function download() {
  downloading.value = true
  try { await filesApi.download(props.part.file_id, props.part.name) }
  catch (error) {
    if ([404, 410].includes(error.response?.status)) { deleted.value = true; emit('deleted', props.part.file_id) }
  } finally { downloading.value = false }
}
function remove() {
  Modal.confirm({
    title: `删除文件「${props.part.name}」？`,
    content: '这会删除实体文件，所有聊天中的引用都将无法下载或供智能体读取。',
    okText: '删除文件', okType: 'danger', cancelText: '取消',
    async onOk() {
      await filesApi.remove(props.part.file_id)
      deleted.value = true
      emit('deleted', props.part.file_id)
      message.success('文件已删除')
    },
  })
}
</script>

<template>
  <div class="chat-file-card">
    <FileTextOutlined />
    <div class="file-info"><strong>{{ part.name || '文件' }}</strong><small>{{ fileSize(part.size || 0) }}<span v-if="unavailable"> · 文件已删除</span></small></div>
    <a-button :disabled="unavailable" :loading="downloading" size="small" @click="download"><DownloadOutlined /> 下载</a-button>
    <a-button v-if="part.metadata?.owner_user_id === auth.user?.user_id && !unavailable" size="small" danger aria-label="删除文件" @click="remove"><DeleteOutlined /></a-button>
  </div>
</template>

<style scoped>
.chat-file-card { display: flex; align-items: center; gap: 10px; padding: 12px; border: 1px solid var(--border-color, #ddd); border-radius: 8px; max-width: 560px; }
.file-info { min-width: 0; flex: 1; }
.file-info strong { display: block; overflow-wrap: anywhere; }
.file-info small { display: block; color: #888; margin-top: 4px; }
</style>
