// 本地文件能力：产物保存到磁盘、Finder 显示、选择本地文件上传。
import { save, open } from '@tauri-apps/plugin-dialog'
import { writeFile, readFile } from '@tauri-apps/plugin-fs'
import { revealItemInDir, openPath } from '@tauri-apps/plugin-opener'
import { isTauri } from './index'

/**
 * 把 Blob 存到用户选择的本地路径。
 * @returns {Promise<string|null>} 保存后的绝对路径；用户取消时返回 null。
 */
export async function saveBlobToDisk(blob, defaultName = 'download') {
  if (!isTauri) return null
  const path = await save({ defaultPath: defaultName })
  if (!path) return null
  const bytes = new Uint8Array(await blob.arrayBuffer())
  await writeFile(path, bytes)
  return path
}

export function revealInFinder(path) {
  return revealItemInDir(path)
}

export function openWithDefaultApp(path) {
  return openPath(path)
}

/**
 * 弹系统文件选择器，读取所选文件，返回 [{ name, path, size, base64, contentType }]。
 * 给「发送本地文件到对话」用：调用方负责走 uploadArtifact。
 */
export async function pickLocalFiles({ multiple = true } = {}) {
  if (!isTauri) return []
  const selection = await open({ multiple, directory: false })
  if (!selection) return []
  const paths = Array.isArray(selection) ? selection : [selection]
  return readLocalFiles(paths)
}

/** 按绝对路径读取本地文件（拖拽进窗口时 Tauri 只给路径）。 */
export async function readLocalFiles(paths) {
  const out = []
  for (const path of paths) {
    const bytes = await readFile(path)
    out.push({
      name: path.split('/').pop() || 'file',
      path,
      size: bytes.byteLength,
      base64: bytesToBase64(bytes),
      contentType: guessContentType(path),
    })
  }
  return out
}

const MIME_BY_EXT = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  svg: 'image/svg+xml',
  pdf: 'application/pdf',
  md: 'text/markdown',
  txt: 'text/plain',
  json: 'application/json',
  csv: 'text/csv',
  html: 'text/html',
  zip: 'application/zip',
}

export function guessContentType(path) {
  const ext = (path.split('.').pop() || '').toLowerCase()
  return MIME_BY_EXT[ext] || 'application/octet-stream'
}

export function isImageContentType(contentType) {
  return typeof contentType === 'string' && contentType.startsWith('image/')
}

export function bytesToBase64(bytes) {
  // 分块编码避免大文件时 String.fromCharCode 栈溢出。
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}
