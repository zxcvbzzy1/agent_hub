import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeToolGroupSelection } from './toolSelection.js'

test('memory and system tools stay selected when switching groups', () => {
  let selected = ['bash', 'file']
  selected = mergeToolGroupSelection(selected, ['manage_memory'], ['manage_memory'])
  assert.deepEqual(selected, ['bash', 'file', 'manage_memory'])
  selected = mergeToolGroupSelection(selected, ['bash', 'file', 'deploy'], ['bash', 'file', 'deploy'])
  assert.deepEqual(new Set(selected), new Set(['manage_memory', 'bash', 'file', 'deploy']))
  selected = mergeToolGroupSelection(selected, ['manage_memory'], [])
  assert.deepEqual(new Set(selected), new Set(['bash', 'file', 'deploy']))
})

test('group deselection preserves tools from collapsed or unloaded groups', () => {
  const selected = ['manage_memory', 'bash', 'search', 'custom_tool']
  assert.deepEqual(mergeToolGroupSelection(selected, ['bash', 'file'], []),
    ['manage_memory', 'search', 'custom_tool'])
})

test('selecting all affects only that group and does not duplicate tools', () => {
  const selected = ['bash', 'manage_memory']
  const all = mergeToolGroupSelection(selected, ['bash', 'file'], ['bash', 'file', 'file'])
  assert.deepEqual(all, ['manage_memory', 'bash', 'file'])
  assert.deepEqual(mergeToolGroupSelection(all, ['bash', 'file'], []), ['manage_memory'])
})
