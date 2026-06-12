// App 启动时的桌面端初始化：通知权限预热 + 按设置自动拉起本地服务。
import { message } from 'ant-design-vue'
import { isTauri } from './index'
import { warmupNotificationPermission } from './notify'
import { procApi } from './processes'

export function bootstrapDesktop() {
  if (!isTauri) return
  warmupNotificationPermission()
  procApi
    .getSettings()
    .then((settings) => {
      if (!settings?.auto_start) return null
      message.loading({ content: '正在拉起本地服务（MongoDB / im_backend）…', key: 'proc-autostart', duration: 0 })
      return procApi
        .startAll()
        .then((report) => {
          message.success({ content: report.join('；'), key: 'proc-autostart', duration: 4 })
        })
        .catch((error) => {
          message.error({ content: `自动启动失败：${error}`, key: 'proc-autostart', duration: 6 })
        })
    })
    .catch(() => {})
}
