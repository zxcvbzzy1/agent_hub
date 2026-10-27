import test from 'node:test'
import assert from 'node:assert/strict'
import { collectDirectoryDrop, workspaceManifest } from './workspaceImport.js'

test('manifest keeps relative paths and rejects duplicate or unsafe targets', () => {
  const files = [{ path: 'project/src/a.txt', file: { size: 4 } }]
  assert.deepEqual(workspaceManifest(files, ['project/empty']).directories, ['project/empty'])
  assert.throws(() => workspaceManifest([...files, ...files]))
  assert.throws(() => workspaceManifest([{ path: '../outside', file: { size: 1 } }]))
  assert.throws(() => workspaceManifest(files, [], { files: 1, file_bytes: 2, total_bytes: 10 }))
  assert.throws(() => workspaceManifest(files, [], { files: 1, file_bytes: 10, total_bytes: 2 }))
})

function directory(name, batches) {
  return { name, isDirectory: true, createReader() {
    const pending = [...batches, []]
    return { readEntries(resolve) { resolve(pending.shift()) } }
  } }
}

test('drop reads every directory batch and preserves empty directories', async () => {
  const file = { name: 'a', isDirectory: false, file(resolve) { resolve({ name: 'a', size: 1 }) } }
  const entry = directory('project', [[directory('empty', [])], [file]])
  const imported = await collectDirectoryDrop([{ kind: 'file', webkitGetAsEntry: () => entry }])
  assert.deepEqual(imported.paths, ['project/a'])
  assert.deepEqual(imported.directories, ['project', 'project/empty'])
})

test('drop requires a directory and supports cancellation', async () => {
  await assert.rejects(collectDirectoryDrop([{ kind: 'file', webkitGetAsEntry: () => ({ isDirectory: false }) }]))
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(collectDirectoryDrop([{ kind: 'file', webkitGetAsEntry: () => directory('p', []) }], undefined, controller.signal))
})
