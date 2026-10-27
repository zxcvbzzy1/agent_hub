<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import ChatAttachments from './ChatAttachments.vue'

const props = defineProps({
  items: { type: Array, default: () => [] }, targetKey: String, disabled: Boolean,
  active: { type: Boolean, default: true },
  memoryWriteEnabled: Boolean, memorySaving: Boolean,
  group: Boolean, workdir: String, effectiveWorkdir: String, workspaceBusy: Boolean, importProgress: Number,
})
defineEmits(['upload', 'reuse', 'remove', 'retry', 'memory-change', 'update:workdir', 'save-workdir', 'import-drop', 'import-files', 'cancel-import'])
const folderPicker = ref(null)
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
          <section class="run-setting">
            <div class="setting-label"><strong>将本次流程写入长期记忆</strong><a-switch :checked="memoryWriteEnabled" :loading="memorySaving" :disabled="disabled || memorySaving" aria-label="将本次流程写入长期记忆" @change="$emit('memory-change', $event)" /></div>
            <small>关闭仍可读取已有记忆。设置在当前聊天内保持；明确要求记住、更正或忘记时仍可修改记忆。</small>
          </section>
          <section v-if="group" class="run-setting">
            <strong>群工作目录</strong>
            <a-input :value="workdir" :disabled="disabled || workspaceBusy" placeholder="后端已有绝对路径，留空使用默认目录" aria-label="群工作目录" @update:value="$emit('update:workdir', $event)" />
            <small>当前：{{ effectiveWorkdir || '后端默认目录' }}。群内全部智能体的新任务共用此路径。</small>
            <a-button size="small" :disabled="disabled || workspaceBusy" @click="$emit('save-workdir')">保存路径</a-button>
            <div class="directory-drop" role="button" tabindex="0" :aria-disabled="disabled || workspaceBusy" @dragover.prevent @drop.prevent.stop="!disabled && !workspaceBusy && $emit('import-drop', $event.dataTransfer)" @click="!disabled && !workspaceBusy && folderPicker?.click()" @keydown.enter="!disabled && !workspaceBusy && folderPicker?.click()">
              {{ workspaceBusy ? '正在处理目录…' : '拖入文件夹，或点击选择文件夹' }}
              <small>上传副本作为工作目录，保留目录结构。</small>
            </div>
            <input ref="folderPicker" hidden type="file" webkitdirectory multiple :disabled="disabled || workspaceBusy" @change="$emit('import-files', $event.target.files); $event.target.value = ''" />
            <template v-if="workspaceBusy"><a-progress :percent="importProgress || 0" size="small" /><a-button size="small" @click="$emit('cancel-import')">取消导入</a-button></template>
          </section>
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
.run-setting { display: grid; gap: 8px; padding-bottom: 14px; margin-bottom: 14px; border-bottom: 1px solid var(--border, #e5e7eb); }
.run-setting small { color: var(--muted, #707782); font-size: 12px; overflow-wrap: anywhere; }
.setting-label { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.directory-drop { display: grid; gap: 4px; border: 1px dashed #aab4c5; border-radius: 8px; padding: 12px; cursor: pointer; font-size: 12px; }
</style>
