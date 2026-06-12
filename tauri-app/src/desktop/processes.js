// 进程托管（mongod + im_backend）的前端封装，对应 src-tauri/src/process_manager.rs。
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'

export const procApi = {
  getSettings() {
    return invoke('get_proc_settings')
  },
  saveSettings(settings) {
    return invoke('save_proc_settings', { settings })
  },
  status() {
    return invoke('proc_status')
  },
  logs(kind) {
    return invoke('proc_logs', { kind })
  },
  start(kind) {
    return invoke('start_proc', { kind })
  },
  stop(kind) {
    return invoke('stop_proc', { kind })
  },
  restart(kind) {
    return invoke('restart_proc', { kind })
  },
  startAll() {
    return invoke('start_all')
  },
  onLog(handler) {
    return listen('proc-log', (event) => handler(event.payload))
  },
  onExit(handler) {
    return listen('proc-exit', (event) => handler(event.payload))
  },
}
