// 系统通知：仅在窗口未聚焦时打扰，用于 agent 回复完成 / 失败 / 等待人工确认。
import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from '@tauri-apps/plugin-notification'
import { isTauri } from './index'

let permissionReady = null

async function ensurePermission() {
  if (!isTauri) return false
  if (!permissionReady) {
    permissionReady = (async () => {
      if (await isPermissionGranted()) return true
      const result = await requestPermission()
      return result === 'granted'
    })()
  }
  return permissionReady
}

/** 窗口聚焦时不打扰；未聚焦时发系统通知。 */
export async function notifyIfUnfocused(title, body) {
  if (!isTauri) return
  if (typeof document !== 'undefined' && document.hasFocus()) return
  if (!(await ensurePermission())) return
  sendNotification({ title, body: body || '' })
}

/** App 启动时预热权限请求，避免第一条通知时才弹授权框。 */
export function warmupNotificationPermission() {
  ensurePermission().catch(() => {})
}
