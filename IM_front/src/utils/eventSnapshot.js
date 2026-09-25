// Events and their checkpoint are committed in one IndexedDB transaction.
// localStorage is a convenience mirror, never evidence that history is present.
const DB_NAME = 'agent-im-events-v3'
const STORE = 'snapshots'
const PREFIX = 'agent-im-stream-v3:'
const TTL = 2 * 24 * 60 * 60 * 1000
let database

function openDatabase() {
  if (!database) database = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'key' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  }).catch(error => { database = null; throw error })
  return database
}

export function snapshotKey(url, userId) {
  const parsed = new URL(url, globalThis.location?.href)
  parsed.searchParams.delete('last_id')
  parsed.searchParams.sort()
  return JSON.stringify([parsed.origin, userId, parsed.pathname, parsed.search])
}

function mirror(key, cursor) {
  try {
    if (cursor) localStorage.setItem(PREFIX + key, cursor)
    else localStorage.removeItem(PREFIX + key)
  } catch { /* IndexedDB remains authoritative when localStorage is unavailable. */ }
}

export function compareCursor(a, b) {
  if (!a) return -1
  if (!b) return 1
  const [ga, ca] = a.split('/')
  const [gb, cb] = b.split('/')
  if (ga !== gb || !ca || !cb) return null
  const [am, as] = ca.split('-').map(BigInt)
  const [bm, bs] = cb.split('-').map(BigInt)
  return am < bm ? -1 : am > bm ? 1 : as < bs ? -1 : as > bs ? 1 : 0
}

export class EventSnapshot {
  constructor(key, userId) { Object.assign(this, { key, userId, revision: null }) }

  async transaction(update) {
    const db = await openDatabase()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      const store = tx.objectStore(STORE)
      const request = store.get(this.key)
      let result
      request.onsuccess = () => {
        try { result = update(request.result, store) } catch (error) { tx.abort(); reject(error) }
      }
      tx.oncomplete = () => resolve(result)
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error || new Error('Snapshot transaction aborted'))
    })
  }

  async load() {
    const value = await this.transaction((existing, store) => {
      if (existing?.complete && existing.updatedAt > Date.now() - TTL
          && Array.isArray(existing.events) && existing.events.every(event => event && typeof event.event_id === 'string' && typeof event.name === 'string')
          && /^[^/]+\/\d+-\d+$/.test(existing.cursor || '') && existing.revision) return existing
      const fresh = { key: this.key, userId: this.userId, revision: crypto.randomUUID(),
        events: [], cursor: '', complete: false, updatedAt: Date.now() }
      // Keep an in-progress tab's revision so simultaneous cold tabs can merge.
      if (existing && !existing.complete && existing.updatedAt > Date.now() - TTL) fresh.revision = existing.revision
      store.put(fresh)
      return fresh
    })
    this.revision = value.revision
    mirror(this.key, value.complete ? value.cursor : '')
    return value.complete ? value : null
  }

  async reset() {
    const revision = crypto.randomUUID()
    await this.transaction((_, store) => store.put({ key: this.key, userId: this.userId,
      revision, events: [], cursor: '', complete: false, updatedAt: Date.now() }))
    this.revision = revision
    mirror(this.key, '')
  }

  async save(events, cursor) {
    const checkpoint = await this.transaction((existing, store) => {
      // A reset/logout in another tab must not be undone by an old in-flight write.
      if (!existing || existing.revision !== this.revision) return null
      const comparison = compareCursor(cursor, existing.cursor)
      if (existing.cursor && comparison === null) return null
      const merged = new Map(existing.events.map(event => [event.event_id, event]))
      for (const event of events) merged.set(event.event_id, event)
      const next = comparison < 0 ? existing.cursor : cursor
      store.put({ ...existing, events: [...merged.values()], cursor: next,
        complete: true, updatedAt: Date.now() })
      return next
    })
    if (checkpoint === null) throw new Error('Snapshot was invalidated by another tab')
    mirror(this.key, checkpoint)
  }

  invalidateMirror() { mirror(this.key, '') }
}

export async function clearEventSnapshots(userId) {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(PREFIX) && JSON.parse(key.slice(PREFIX.length))[1] === userId) localStorage.removeItem(key)
    }
  } catch { /* Storage may be unavailable. */ }
  try {
    const db = await openDatabase()
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      const request = tx.objectStore(STORE).openCursor()
      request.onsuccess = () => {
        const cursor = request.result
        if (!cursor) return
        if (cursor.value.userId === userId || cursor.value.updatedAt < Date.now() - TTL) cursor.delete()
        cursor.continue()
      }
      tx.oncomplete = resolve
      tx.onerror = () => reject(tx.error)
    })
  } catch { /* Logout must succeed even when IndexedDB is blocked. */ }
}
