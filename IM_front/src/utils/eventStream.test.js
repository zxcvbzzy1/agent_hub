import 'fake-indexeddb/auto'
import test from 'node:test'
import assert from 'node:assert/strict'
import { EventSnapshot, snapshotKey, clearEventSnapshots } from './eventSnapshot.js'
import { EventStream, clearUserEventStreams } from './eventStream.js'

const storage = {}
globalThis.localStorage = {
  getItem: key => storage[key] ?? null,
  setItem: (key, value) => { storage[key] = String(value) },
  removeItem: key => { delete storage[key] },
}
const event = id => ({ event_id: id, name: 'tool.called', version: 2, created_at: 1, payload: {} })
const key = user => snapshotKey('https://example.test/api/im/runs/r/events/stream', user)
const waitFor = async predicate => {
  for (let i = 0; i < 100; i++) {
    if (predicate()) return
    await new Promise(resolve => setTimeout(resolve, 5))
  }
  assert.fail('condition not reached')
}

function login(userId) {
  localStorage.setItem('agent-im-auth', JSON.stringify({ token: 'secret', user: { user_id: userId } }))
}

test('localStorage cursor alone cannot resume without its complete IndexedDB snapshot', async () => {
  const user = crypto.randomUUID()
  localStorage.setItem('agent-im-stream-v3:' + key(user), 'g/99-0')
  const snapshot = new EventSnapshot(key(user), user)
  assert.equal(await snapshot.load(), null)
  assert.equal(localStorage.getItem('agent-im-stream-v3:' + key(user)), null)
  await snapshot.save([event('a')], 'g/1-0')
  const other = new EventSnapshot(key(user), user)
  assert.deepEqual((await other.load()).events, [event('a')])
  assert.equal(localStorage.getItem('agent-im-stream-v3:' + key(user)), 'g/1-0')
})

test('concurrent tabs merge events and never move the shared checkpoint backward', async () => {
  const user = crypto.randomUUID()
  const first = new EventSnapshot(key(user), user)
  const second = new EventSnapshot(key(user), user)
  await Promise.all([first.load(), second.load()])
  await Promise.all([first.save([event('a'), event('b')], 'g/2-0'), second.save([event('a')], 'g/1-0')])
  const restored = await new EventSnapshot(key(user), user).load()
  assert.equal(restored.cursor, 'g/2-0')
  assert.deepEqual(new Set(restored.events.map(e => e.event_id)), new Set(['a', 'b']))
})

test('reset and logout fence late writes from old tabs', async () => {
  const user = crypto.randomUUID()
  const first = new EventSnapshot(key(user), user)
  const stale = new EventSnapshot(key(user), user)
  await first.load()
  await first.save([event('deleted')], 'old/1-0')
  await stale.load()
  await first.reset()
  await assert.rejects(stale.save([event('deleted')], 'old/2-0'))
  await first.save([event('new')], 'new/3-0')
  assert.deepEqual((await new EventSnapshot(key(user), user).load()).events, [event('new')])
  await clearEventSnapshots(user)
  await assert.rejects(first.save([event('new')], 'new/4-0'))
})

test('cache keys isolate users, servers and filtered views', () => {
  const base = 'https://example.test/events'
  assert.notEqual(snapshotKey(base, 'a'), snapshotKey(base, 'b'))
  assert.notEqual(snapshotKey(base, 'a'), snapshotKey('https://other.test/events', 'a'))
  assert.notEqual(snapshotKey(base, 'a'), snapshotKey(base + '?execution_id=x', 'a'))
  assert.equal(snapshotKey(base, 'a'), snapshotKey(base + '?last_id=g/1-0', 'a'))
})

test('malformed local history cannot authorize a cursor-only resume', async () => {
  const user = crypto.randomUUID()
  const snapshot = new EventSnapshot(key(user), user)
  await snapshot.load()
  await snapshot.transaction((existing, store) => store.put({ ...existing, complete: true,
    cursor: 'broken', events: [null] }))
  assert.equal(await new EventSnapshot(key(user), user).load(), null)
})


class NativeSource {
  constructor(url) { this.url = url; this.listeners = new Map(); this.readyState = 0 }
  addEventListener(name, handler) { this.listeners.set(name, handler) }
  send(item, id = '') {
    this.listeners.get(item.name)?.({ data: JSON.stringify(item), lastEventId: id })
  }
  error(state) { this.readyState = state; this.onerror?.() }
  close() { this.readyState = 2; this.closed = true }
}
const control = name => ({ name: 'stream.' + name, payload: {} })
async function setup(options = {}) {
  const user = crypto.randomUUID()
  login(user)
  const sources = []
  const calls = []
  const url = 'https://example.test/api/im/runs/r/events/stream'
  const stream = new EventStream(url, {
    authenticate: async (_, force) => { calls.push(Boolean(force)) },
    sourceFactory: target => { const source = new NativeSource(target); sources.push(source); return source },
    ...options,
  })
  await waitFor(() => sources.length || stream.closed)
  return { user, stream, sources, calls }
}
async function drain(stream) { await stream.processing; await stream.saving }

test('restores local snapshot before native connection with query cursor, without Bearer in URL', async () => {
  const user = crypto.randomUUID()
  login(user)
  const snapshot = new EventSnapshot(key(user), user)
  await snapshot.load()
  await snapshot.save([event('a')], 'g/1-0')
  let restored = false
  let source
  const stream = new EventStream('https://example.test/api/im/runs/r/events/stream', {
    authenticate: async () => { assert.equal(restored, true) },
    sourceFactory: target => { assert.equal(restored, true); source = new NativeSource(target); return source },
  })
  stream.addEventListener('stream.restore', raw => { restored = true; assert.deepEqual(JSON.parse(raw.data), [event('a')]) })
  try {
    await waitFor(() => source)
    assert.equal(new URL(source.url).searchParams.get('last_id'), 'g/1-0')
    assert.ok(!source.url.includes('secret'))
    source.send(control('ready'), 'g/1-0')
    source.send(event('b'), 'g/2-0')
    source.send(control('checkpoint'), 'g/3-0')
    await drain(stream)
    await stream.persist()
    const saved = await new EventSnapshot(key(user), user).load()
    assert.equal(saved.cursor, 'g/3-0')
    assert.deepEqual(saved.events.map(e => e.event_id), ['a', 'b'])
  } finally { stream.close() }
})

test('native reconnect keeps one source and serializes reset, history and ready across disconnects', async () => {
  const { stream, sources, user, calls } = await setup()
  const received = []
  stream.addEventListener('tool.called', async raw => {
    await new Promise(resolve => setTimeout(resolve, 5))
    received.push(JSON.parse(raw.data).event_id)
  })
  try {
    const source = sources[0]
    source.send(control('reset'))
    source.send(event('partial'))
    source.error(0)
    source.send(control('reset'))
    source.send(event('complete'))
    source.send(control('ready'), 'g/1-0')
    source.send(event('live'), 'g/2-0')
    source.send(event('live'), 'g/2-0')
    await drain(stream)
    await stream.persist()
    assert.deepEqual(received, ['partial', 'complete', 'live'])
    assert.equal(sources.length, 1)
    assert.deepEqual(calls, [false])
    const saved = await new EventSnapshot(key(user), user).load()
    assert.deepEqual(saved.events.map(e => e.event_id), ['complete', 'live'])
    assert.equal(saved.cursor, 'g/2-0')
  } finally { stream.close() }
})

test('partial bootstrap and reset checkpoint are never marked complete', async () => {
  const { stream, sources, user } = await setup()
  sources[0].send(control('reset'))
  sources[0].send(event('partial'))
  sources[0].send(control('checkpoint'), 'g/9-0')
  await drain(stream)
  await stream.persist()
  assert.equal(await new EventSnapshot(key(user), user).load(), null)
  await clearUserEventStreams(user)
  assert.equal(stream.closed, true)
})

test('CLOSED refreshes Cookie once and resumes this page position, then stops with terminal error', async () => {
  const { stream, sources, user, calls } = await setup()
  const errors = []
  stream.onerror = raw => errors.push(raw.terminal)
  try {
    sources[0].send(control('ready'), 'g/1-0')
    await drain(stream)
    const other = new EventSnapshot(key(user), user)
    await other.load()
    await other.save([event('other')], 'g/99-0')
    sources[0].error(2)
    await drain(stream)
    assert.equal(new URL(sources[1].url).searchParams.get('last_id'), 'g/1-0')
    assert.deepEqual(calls, [false, true])
    sources[1].error(2)
    await drain(stream)
    assert.equal(stream.closed, true)
    assert.equal(errors.at(-1), true)
    assert.equal(sources.length, 2)
  } finally { stream.close() }
})

test('failed event handler never advances application checkpoint or consumes later queued events', async () => {
  const { stream, sources, user } = await setup()
  const errors = []
  stream.onerror = raw => errors.push(raw.terminal)
  stream.addEventListener('tool.called', () => { throw new Error('consumer failed') })
  sources[0].send(control('ready'), 'g/1-0')
  sources[0].send(event('failed'), 'g/2-0')
  sources[0].send(control('checkpoint'), 'g/3-0')
  await drain(stream)
  assert.equal(stream.closed, true)
  assert.equal(stream.cursor, 'g/1-0')
  assert.equal((await new EventSnapshot(key(user), user).load()).cursor, 'g/1-0')
  assert.equal(errors.at(-1), true)
})

test('storage failure leaves live messages and traces working without advancing persistent cursor', async () => {
  let invalidated = false
  const { stream, sources } = await setup({ snapshotFactory: () => ({
    load: async () => null, reset: async () => {}, save: async () => { throw new Error('quota') },
    invalidateMirror: () => { invalidated = true },
  }) })
  const names = ['workflow.started', 'message.created', 'workflow.finished']
  const received = []
  for (const name of names) stream.addEventListener(name, raw => received.push(JSON.parse(raw.data).name))
  try {
    sources[0].send(control('ready'), 'g/0-0')
    names.forEach((name, index) => sources[0].send({ ...event(String(index)), name }, `g/${index + 1}-0`))
    await drain(stream)
    assert.deepEqual(received, names)
    assert.equal(invalidated, true)
    assert.equal(stream.persistence, false)
    assert.equal(stream.pending.size, 0)
  } finally { stream.close() }
})

test('logout fences queued events and an unfinished Cookie initialization', async () => {
  const user = crypto.randomUUID()
  login(user)
  let release
  let connections = 0
  const stream = new EventStream('https://example.test/events', {
    authenticate: () => new Promise(resolve => { release = resolve }),
    sourceFactory: () => { connections++; return new NativeSource('') },
  })
  await waitFor(() => release)
  await clearUserEventStreams(user)
  release()
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.equal(connections, 0)
  assert.equal(stream.closed, true)
})

test('logout waits for an in-flight reset and discards later native callbacks', async () => {
  let release
  let resetFinished = false
  const { stream, sources, user } = await setup({ snapshotFactory: () => ({
    load: async () => null, invalidateMirror: () => {},
    reset: () => new Promise(resolve => { release = () => { resetFinished = true; resolve() } }),
  }) })
  let received = 0
  stream.addEventListener('tool.called', () => { received++ })
  sources[0].send(control('reset'))
  await waitFor(() => release)
  sources[0].send(event('late'), 'g/1-0')
  let cleared = false
  const logout = clearUserEventStreams(user).then(() => { cleared = true })
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.equal(cleared, false)
  release()
  await logout
  await drain(stream)
  assert.equal(resetFinished, true)
  assert.equal(received, 0)
})

test('account switch during Cookie setup cannot connect the old identity', async () => {
  const user = crypto.randomUUID()
  login(user)
  let release
  let connections = 0
  const stream = new EventStream('https://example.test/events', {
    authenticate: () => new Promise(resolve => { release = resolve }),
    sourceFactory: () => { connections++; return new NativeSource('') },
  })
  await waitFor(() => release)
  login('different-user')
  release()
  await waitFor(() => stream.closed)
  assert.equal(connections, 0)
})
