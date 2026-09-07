import { computed, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { filesApi } from '@/api/files'

export function useChatFiles(targetKey) {
  const drafts = reactive({})
  function forKey(key) {
    return drafts[key] ||= { requestId: crypto.randomUUID(), text: '', items: [], mentions: [], reply: null, quote: null, selection: null }
  }
  function moveDraft(from, key) { drafts[key] = from }
  const draft = computed(() => forKey(targetKey.value))
  const busy = computed(() => draft.value.items.some((item) => item.state !== 'ready'))

  async function uploadItem(item) {
    item.state = 'uploading'
    item.progress = 0
    try {
      const response = await filesApi.upload(item.raw, (event) => {
        item.progress = Math.min(99, Math.round(100 * event.loaded / (event.total || item.size || 1)))
      })
      item.file = response.item
      item.state = 'ready'
      item.progress = 100
      if (item.removed) await filesApi.remove(response.item.file_id)
    } catch {
      item.state = 'failed'
    }
  }
  function uploadFiles(files) {
    const current = draft.value
    const selected = Array.from(files)
    if (current.items.length + selected.length > 10) {
      message.warning('每条消息最多 10 个附件')
      return
    }
    if (selected.some((file) => file.size > 20 * 1024 * 1024)) {
      message.warning('单文件不能超过 20 MiB')
      return
    }
    for (const raw of selected) {
      const item = reactive({ key: crypto.randomUUID(), name: raw.name, size: raw.size, raw, state: 'uploading', progress: 0, reused: false })
      current.items.push(item)
      uploadItem(item)
    }
  }
  function addExisting(file) {
    if (draft.value.items.some((item) => item.file?.file_id === file.file_id)) return
    if (draft.value.items.length >= 10) { message.warning('每条消息最多 10 个附件'); return }
    draft.value.items.push({ key: crypto.randomUUID(), file, name: file.original_name, size: file.size, reused: true, state: 'ready' })
  }
  async function removeItem(item) {
    const current = draft.value
    if (item.file && !item.reused) {
      try { await filesApi.remove(item.file.file_id) } catch { return }
    }
    item.removed = true
    current.items = current.items.filter((entry) => entry.key !== item.key)
  }
  function markDeleted(fileId) {
    for (const current of Object.values(drafts)) {
      for (const item of current.items) {
        if (item.file?.file_id === fileId) item.state = 'deleted'
      }
    }
  }
  return { draft, busy, forKey, moveDraft, uploadFiles, addExisting, removeItem, retry: uploadItem, markDeleted }
}
