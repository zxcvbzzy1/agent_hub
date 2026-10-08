<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import ChatAttachments from './ChatAttachments.vue'

const props = defineProps({
  items: { type: Array, default: () => [] }, targetKey: String, disabled: Boolean,
  active: { type: Boolean, default: true },
})
defineEmits(['upload', 'reuse', 'remove', 'retry'])
const open = ref(false)
const trigger = ref(null)
const hint = computed(() => {
  const parts = []
  const uploading = props.items.filter(item => item.state === 'uploading').length
  const failed = props.items.filter(item => item.state === 'failed').length
  const deleted = props.items.filter(item => item.state === 'deleted').length
  if (uploading) parts.push(`${uploading} 个上传中`)
  if (failed) parts.push(`${failed} 个上传失败`)
  if (deleted) parts.push(`${deleted} 个已删除`)
  return parts.join(' · ')
})
watch(() => [props.targetKey, props.active], () => { open.value = false })
function escape(event) {
  if (event.key !== 'Escape' || !open.value) return
  open.value = false
  event.preventDefault()
  event.stopImmediatePropagation()
  trigger.value?.$el?.focus()
}
onMounted(() => document.addEventListener('keydown', escape, true))
onUnmounted(() => document.removeEventListener('keydown', escape, true))
</script>

<template>
  <div class="composer-extensions">
    <a-popover v-model:open="open" trigger="click" placement="topLeft" :auto-adjust-overflow="true">
      <template #content>
        <div class="composer-extension-panel" aria-label="扩展操作">
          <strong>附件</strong>
          <ChatAttachments :items="items" :target-key="targetKey" :disabled="disabled" :active="active"
            @picker-open="open = false" @upload="$emit('upload', $event)" @reuse="$emit('reuse', $event)"
            @remove="$emit('remove', $event)" @retry="$emit('retry', $event)" />
        </div>
      </template>
      <a-button ref="trigger" class="extension-trigger" type="text" size="small" :disabled="disabled"
        :aria-expanded="open" aria-label="扩展操作" title="扩展操作">
        <PlusOutlined :rotate="open ? 45 : 0" />
        <span v-if="items.length" class="attachment-count">{{ items.length }}</span>
      </a-button>
    </a-popover>
    <span v-if="hint" class="attachment-hint" role="status">{{ hint }}</span>
  </div>
</template>

<style scoped>
.composer-extensions { display: flex; align-items: center; gap: 6px; min-width: 0; }
.extension-trigger { display: inline-flex; align-items: center; justify-content: center; gap: 5px; min-width: 28px; }
.attachment-count { color: var(--muted, #707782); font-size: 11px; }
.attachment-hint { color: var(--muted, #707782); font-size: 12px; overflow-wrap: anywhere; }
.composer-extension-panel { width: 336px; max-width: calc(100vw - 56px); max-height: min(420px, 60vh); overflow-y: auto; }
.composer-extension-panel > strong { font-size: 13px; color: var(--text, #30343b); }
.composer-extension-panel :deep(.chat-attachments) { margin-bottom: 0; }
.composer-extension-panel :deep(.big-box) { grid-template-columns: minmax(0, 1fr); }
.composer-extension-panel :deep(.draft-file) { flex-wrap: wrap; gap: 6px; font-size: 12px; }
.composer-extension-panel :deep(.file-name) { flex-basis: 100px; }
</style>
