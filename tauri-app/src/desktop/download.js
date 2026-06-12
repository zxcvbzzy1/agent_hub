// 产物落盘：桌面端走系统保存对话框 + 写本地磁盘 + Finder 显示；浏览器里退回 anchor 下载。
import { h } from 'vue'
import { Button, notification, message } from 'ant-design-vue'
import { isTauri } from './index'
import { saveBlobToDisk, revealInFinder } from './files'

function anchorDownloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function anchorDownloadUrl(fileUrl, filename) {
  const anchor = document.createElement('a')
  anchor.href = fileUrl
  anchor.download = filename
  anchor.target = '_blank'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

function notifySaved(path) {
  notification.success({
    message: '已保存到本地',
    description: path,
    duration: 6,
    btn: h(
      Button,
      { type: 'link', size: 'small', onClick: () => revealInFinder(path).catch(() => {}) },
      () => '在 Finder 中显示',
    ),
  })
}

/** Blob 落盘；返回保存路径（浏览器环境或用户取消返回 null）。 */
export async function deliverBlob(blob, filename) {
  if (!isTauri) {
    anchorDownloadBlob(blob, filename)
    return null
  }
  try {
    const path = await saveBlobToDisk(blob, filename)
    if (path) notifySaved(path)
    return path
  } catch (error) {
    message.error(`保存失败：${error}`)
    return null
  }
}

/** URL 资源落盘：桌面端先 fetch 成 Blob 再走保存对话框。 */
export async function deliverUrl(fileUrl, filename) {
  if (!isTauri) {
    anchorDownloadUrl(fileUrl, filename)
    return null
  }
  try {
    const response = await fetch(fileUrl)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const blob = await response.blob()
    return deliverBlob(blob, filename)
  } catch (error) {
    message.error(`下载失败：${error}`)
    return null
  }
}
