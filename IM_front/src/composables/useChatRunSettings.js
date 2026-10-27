import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { imApi } from '@/api/im'
import { collectDirectoryDrop, defaultWorkspaceLimits, workspaceForm, workspaceManifest } from '@/utils/workspaceImport'

export function useChatRunSettings(im, draftKey) {
  const overrides = reactive({})
  const scope = computed(() => im.currentRoom?.type === 'group' ? im.currentGroupConversation : im.currentConversation)
  const memoryEnabled = computed(() => overrides[draftKey.value] ?? scope.value?.memory_write_enabled ?? false)
  const memorySaving = ref(false)
  async function setMemoryEnabled(value) {
    const key = draftKey.value, previous = memoryEnabled.value, conversation = scope.value
    overrides[key] = value
    if (!conversation?.conversation_id) return
    memorySaving.value = true
    try {
      const response = await imApi.updateConversation(conversation.conversation_id, { memory_write_enabled: value })
      Object.assign(conversation, response.item)
    } catch { overrides[key] = previous }
    finally { memorySaving.value = false }
  }

  const roomId = computed(() => im.currentRoom?.type === 'group' ? im.currentRoom.room_id : '')
  const workdir = ref('')
  const effectiveWorkdir = ref('')
  const limits = ref(defaultWorkspaceLimits)
  const workspaceBusy = ref(false)
  const progress = ref(0)
  let controller
  watch([roomId, () => im.currentRoom?.metadata?.workdir], async ([id, path]) => {
    workdir.value = path || ''
    effectiveWorkdir.value = path || ''
    if (!id) return
    try {
      const response = await imApi.roomWorkspace(id)
      if (roomId.value === id) {
        effectiveWorkdir.value = response.item.effective_workdir
        limits.value = response.item.limits
      }
    } catch { /* The HTTP interceptor reports the error. */ }
  }, { immediate: true })
  watch(roomId, () => controller?.abort())
  onUnmounted(() => controller?.abort())
  async function saveWorkdir() {
    const id = roomId.value
    if (!id || workspaceBusy.value) return
    workspaceBusy.value = true
    try {
      await im.updateRoom(id, { metadata: { workdir: workdir.value.trim() } })
      message.success('群工作目录已更新，后续新任务使用此路径')
    } finally { workspaceBusy.value = false }
  }
  async function runImport(collect) {
    const id = roomId.value
    if (!id || workspaceBusy.value) return
    controller = new AbortController()
    const signal = controller.signal
    workspaceBusy.value = true
    progress.value = 0
    try {
      const imported = await collect(signal)
      if (signal.aborted) return
      const response = await imApi.importWorkspace(id, workspaceForm(imported), {
        signal, timeout: 0,
        onUploadProgress: event => { progress.value = Math.round(event.loaded * 100 / (event.total || 1)) },
      })
      if (roomId.value === id) {
        im.currentRoom = response.item
        im.currentGroupRoom = response.item
      }
      await im.fetchRooms()
      message.success('目录已导入并设为群工作目录')
    } catch (error) {
      if (!signal.aborted && !error.response) message.error(error.message || '目录导入失败')
    } finally { workspaceBusy.value = false; controller = null }
  }
  function importDrop(dataTransfer) {
    return runImport(signal => collectDirectoryDrop(dataTransfer.items, limits.value, signal))
  }
  function importFiles(list) {
    return runImport(async () => {
      const files = Array.from(list).map(file => ({ file, path: file.webkitRelativePath || file.name }))
      return { files, ...workspaceManifest(files, [], limits.value) }
    })
  }
  return { memoryEnabled, memorySaving, setMemoryEnabled, workdir, effectiveWorkdir, workspaceBusy,
    progress, saveWorkdir, importDrop, importFiles, cancelImport: () => controller?.abort() }
}
