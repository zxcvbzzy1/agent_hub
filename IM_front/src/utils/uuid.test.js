import 'fake-indexeddb/auto'
import test from 'node:test'
import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { createUUID } from './uuid.js'
import { EventSnapshot, snapshotKey } from './eventSnapshot.js'

function replaceGlobal(t, name, value) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, name)
  Object.defineProperty(globalThis, name, { configurable: true, value })
  t.after(() => {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor)
    else delete globalThis[name]
  })
}

test('uses native randomUUID with its Crypto receiver when available', t => {
  const crypto = {
    randomUUID() {
      assert.equal(this, crypto)
      return 'c974e3ac-57b6-4086-84c4-d0bbc07fc107'
    },
    getRandomValues() { assert.fail('native UUID should be used') },
  }
  replaceGlobal(t, 'crypto', crypto)
  assert.equal(createUUID(), 'c974e3ac-57b6-4086-84c4-d0bbc07fc107')
})

test('generates UUID v4 with secure random bytes when randomUUID is unavailable', t => {
  const crypto = {
    getRandomValues(bytes) {
      assert.equal(this, crypto)
      assert.ok(bytes instanceof Uint8Array)
      assert.equal(bytes.length, 16)
      return bytes.fill(0xff)
    },
  }
  replaceGlobal(t, 'crypto', crypto)
  assert.equal(createUUID(), 'ffffffff-ffff-4fff-bfff-ffffffffffff')
})

test('event snapshots load, save and reset on LAN HTTP without randomUUID', async t => {
  replaceGlobal(t, 'isSecureContext', false)
  replaceGlobal(t, 'crypto', { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) })
  const url = 'http://192.168.1.10:5173/api/im/runs/run/events/stream'
  const key = snapshotKey(url, 'lan-user')
  const first = new EventSnapshot(key, 'lan-user')
  assert.equal(await first.load(), null)
  assert.match(first.revision, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  const events = [{ event_id: 'event-one', name: 'tool.called' }]
  await first.save(events, 'generation/1-0')
  const second = new EventSnapshot(key, 'lan-user')
  assert.deepEqual((await second.load()).events, events)
  const previous = second.revision
  await second.reset()
  assert.notEqual(second.revision, previous)
  await assert.rejects(first.save(events, 'generation/2-0'), /invalidated/)
  await second.remove()
})
