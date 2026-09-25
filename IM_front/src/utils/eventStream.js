import { EventSnapshot, snapshotKey, clearEventSnapshots } from './eventSnapshot.js'
import { sseEventNames } from './runtimeEvents.js'

const active = new Set()
const transient = new Set(['llm.delta', 'agent.delta'])
let cookieInitialization

function session() {
  try { return JSON.parse(localStorage.getItem('agent-im-auth') || 'null') } catch { return null }
}

// Ordinary Axios/Bearer request; shared by all subscriptions on this page.
// Lazy import keeps the HTTP interceptor's logout dependency acyclic at startup.
async function ensureCookie(auth, force = false) {
  if (force || cookieInitialization?.token !== auth.token) {
    const entry = { token: auth.token }
    entry.promise = import('../api/http.js').then(async ({ default: http }) => {
      const result = await http.get('/api/im/auth/me', { headers: { Authorization: `Bearer ${auth.token}` } })
      if (result.item?.user_id !== auth.user?.user_id) throw new Error('登录身份已变化')
    }).catch(error => {
      if (cookieInitialization === entry) cookieInitialization = null
      throw error
    })
    cookieInitialization = entry
  }
  return cookieInitialization.promise
}

// Native EventSource owns the wire protocol and normal reconnects. This adapter
// only orders application work and commits display snapshots/checkpoints.
export class EventStream {
  constructor(url, {
    sourceFactory = target => new EventSource(target),
    authenticate = ensureCookie,
    snapshotFactory = (key, userId) => new EventSnapshot(key, userId),
  } = {}) {
    this.url = new URL(url, globalThis.location?.href).toString()
    this.sourceFactory = sourceFactory
    this.authenticate = authenticate
    const auth = session()
    this.userId = auth?.user?.user_id || ''
    this.token = auth?.token
    this.snapshot = snapshotFactory(snapshotKey(this.url, this.userId), this.userId)
    this.listeners = new Map()
    this.names = new Set([...sseEventNames, 'message', 'stream.reset', 'stream.ready', 'stream.checkpoint'])
    this.closed = false
    this.ready = false
    this.cursor = ''
    this.persistence = true
    this.pending = new Map()
    this.seen = new Set()
    this.saving = Promise.resolve()
    this.processing = Promise.resolve()
    this.recovered = false
    this.initialized = new Promise(resolve => { this.finishInitialization = resolve })
    active.add(this)
    queueMicrotask(() => this.run().catch(error => this.fail(error)))
  }

  addEventListener(name, listener) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set())
    this.listeners.get(name).add(listener)
    if (!this.names.has(name) && !['open', 'error', 'stream.restore'].includes(name)) {
      this.names.add(name)
      if (this.source) this.listen(this.source, name)
    }
  }
  removeEventListener(name, listener) { this.listeners.get(name)?.delete(listener) }
  async emit(type, data = '', lastEventId = '', terminal = false) {
    if (this.closed) return
    const event = { type, data, lastEventId, terminal }
    if (typeof this['on' + type] === 'function') await this['on' + type](event)
    for (const listener of this.listeners.get(type) || []) {
      if (this.closed) return
      await listener(event)
    }
  }
  currentAuth() {
    const auth = session()
    return auth?.token === this.token && auth?.user?.user_id === this.userId ? auth : null
  }
  enqueue(work) {
    this.processing = this.processing.then(() => {
      if (!this.closed) return work()
    }).catch(error => this.fail(error))
  }
  async run() {
    try {
      let restored
      try { restored = await this.snapshot.load() } catch { this.disablePersistence() }
      if (restored && !this.closed) {
        await this.emit('stream.restore', JSON.stringify(restored.events), restored.cursor)
        this.seen = new Set(restored.events.map(item => item.event_id))
        this.cursor = restored.cursor
        this.ready = true
      }
    } finally { this.finishInitialization() }
    if (this.closed) return
    const auth = this.currentAuth()
    if (!auth) { this.close(); return }
    await this.authenticate(auth)
    if (!this.currentAuth()) this.close()
    if (!this.closed) this.connect()
  }
  connect() {
    const url = new URL(this.url)
    // A new object must start from this page's processed checkpoint, never from
    // a different tab's (possibly newer) localStorage mirror.
    url.searchParams.delete('last_id')
    if (this.ready && this.cursor) url.searchParams.set('last_id', this.cursor)
    if (globalThis.location && url.origin !== globalThis.location.origin) {
      throw new Error('事件连接需要同源 /api 代理')
    }
    const source = this.sourceFactory(url.toString())
    this.source = source
    for (const name of this.names) this.listen(source, name)
    source.onopen = () => {
      if (this.source === source) this.enqueue(() => this.emit('open'))
    }
    source.onerror = () => {
      if (this.source !== source || this.closed) return
      if (source.readyState === 2) {
        source.close()
        this.source = null
        this.enqueue(() => this.recover())
      } else this.enqueue(() => this.emit('error'))
    }
  }
  listen(source, name) {
    source.addEventListener(name, event => {
      if (this.source !== source || this.closed) return
      // Capture at receipt; keep queued events across automatic reconnects.
      const frame = { type: name, data: event.data, id: event.lastEventId }
      this.enqueue(() => this.consume(frame))
    })
  }
  async recover() {
    await this.emit('error')
    if (this.recovered) throw new Error('事件连接已关闭，请重试')
    this.recovered = true
    const auth = this.currentAuth()
    if (!auth) { this.close(); return }
    await this.authenticate(auth, true)
    if (!this.currentAuth()) this.close()
    if (!this.closed) this.connect()
  }
  async fail(error) {
    if (this.closed) return
    this.source?.close()
    try { await this.emit('error', error?.message || '事件连接失败', '', true) }
    catch { /* A broken error listener must still close the connection. */ }
    finally { this.close() }
  }

  async consume(frame) {
    if (this.closed) return
    if (frame.type === 'stream.reset') {
      this.ready = false
      this.cursor = ''
      this.pending.clear()
      this.seen.clear()
      clearTimeout(this.saveTimer)
      this.saveTimer = null
      this.saving = this.saving.then(async () => {
        if (this.closed || !this.persistence) return
        try { await this.snapshot.reset() } catch { this.disablePersistence() }
      })
      await this.saving
      await this.emit(frame.type, frame.data)
      return
    }
    if (frame.data) {
      const item = JSON.parse(frame.data)
      if (!item.event_id || !this.seen.has(item.event_id)) {
        await this.emit(frame.type, frame.data, frame.id || '')
        if (this.closed) return
        if (item.event_id) {
          this.seen.add(item.event_id)
          if (this.persistence && !transient.has(item.name)) this.pending.set(item.event_id, item)
        }
      }
    }
    if (frame.id) this.cursor = frame.id
    if (frame.type === 'stream.ready') this.ready = true
    if (this.ready && this.cursor) {
      if (frame.type === 'stream.ready' || this.pending.size >= 100) await this.persist()
      else if (!this.saveTimer) this.saveTimer = setTimeout(() => { this.saveTimer = null; this.persist() }, 200)
    }
  }

  persist() {
    clearTimeout(this.saveTimer)
    this.saveTimer = null
    if (!this.persistence || !this.ready || !this.cursor || this.closed) return this.saving
    const events = [...this.pending.values()]
    const cursor = this.cursor
    this.pending.clear()
    this.saving = this.saving.then(async () => {
      if (this.closed || !this.persistence) return
      try { await this.snapshot.save(events, cursor) } catch { this.disablePersistence() }
    })
    return this.saving
  }
  disablePersistence() {
    this.persistence = false
    this.pending.clear()
    this.snapshot.invalidateMirror()
  }
  close() {
    this.closed = true
    this.source?.close()
    this.source = null
    clearTimeout(this.saveTimer)
    this.pending.clear()
    active.delete(this)
  }
}

export async function clearUserEventStreams(userId) {
  cookieInitialization = null
  const streams = [...active].filter(stream => stream.userId === userId)
  for (const stream of streams) stream.close()
  await Promise.all(streams.map(stream => Promise.all([stream.initialized, stream.saving])))
  await clearEventSnapshots(userId)
}

if (typeof window !== 'undefined') window.addEventListener('storage', event => {
  if (event.key === 'agent-im-auth') {
    cookieInitialization = null
    for (const stream of active) if (!stream.currentAuth()) void clearUserEventStreams(stream.userId)
  }
})
