export const defaultWorkspaceLimits = { file_bytes: 20 * 1024 * 1024, total_bytes: 200 * 1024 * 1024, files: 5000 }

export function workspaceManifest(files, directories = [], limits = defaultWorkspaceLimits) {
  if (files.length > limits.files || directories.length > limits.files) throw new Error('目录中的文件或目录数量超限')
  if (files.some(item => item.file.size > limits.file_bytes)) throw new Error('目录中存在超出大小限制的文件')
  if (files.reduce((sum, item) => sum + item.file.size, 0) > limits.total_bytes) throw new Error('目录总大小超限')
  const paths = files.map(item => item.path)
  const valid = path => typeof path === 'string' && path && !path.includes('\\') && !path.includes('\0') && !path.includes(':') && path.split('/').every(part => part && part !== '.' && part !== '..')
  if (![...paths, ...directories].every(valid)) throw new Error('目录包含无效相对路径')
  if (new Set(paths).size !== paths.length || new Set(directories).size !== directories.length || paths.some(p => directories.includes(p))) throw new Error('目录包含重复目标路径')
  return { paths, directories }
}

export async function collectDirectoryDrop(items, limits = defaultWorkspaceLimits, signal) {
  // Capture entries synchronously while the drop data store is still readable.
  const entries = Array.from(items).filter(item => item.kind === 'file').map(item => item.getAsEntry?.() || item.webkitGetAsEntry?.())
  if (!entries.length || entries.some(entry => !entry?.isDirectory)) throw new Error('请拖入文件夹；也可点击选择文件夹')
  const files = [], directories = []
  async function visit(entry, parent = '') {
    if (signal?.aborted) throw new Error('目录导入已取消')
    const path = parent + entry.name
    if (entry.isDirectory) {
      directories.push(path)
      if (directories.length > limits.files) throw new Error('目录数量超限')
      const reader = entry.createReader()
      while (true) {
        const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject))
        if (!batch.length) break
        for (const child of batch) await visit(child, path + '/')
      }
    } else {
      const file = await new Promise((resolve, reject) => entry.file(resolve, reject))
      files.push({ path, file })
      workspaceManifest(files, directories, limits)
    }
  }
  for (const entry of entries) await visit(entry)
  return { files, ...workspaceManifest(files, directories, limits) }
}

export function workspaceForm(imported) {
  const form = new FormData()
  form.append('manifest', JSON.stringify({ paths: imported.paths, directories: imported.directories }))
  for (const item of imported.files) form.append('files', item.file, item.file.name)
  return form
}
