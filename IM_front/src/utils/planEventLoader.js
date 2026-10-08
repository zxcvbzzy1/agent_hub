import { planDetailEvents } from './composerPlan.js'

// Scope SSE intentionally omits step bodies. Fetch only the selected run's
// business details, keeping them out of the shared conversation event store.
export class PlanEventLoader {
  constructor({ api, changed = () => {} }) {
    this.api = api
    this.changed = changed
    this.epoch = 0
    this.clear()
  }
  clear() {
    this.epoch++
    this.details = new Map()
    this.pending = new Set()
    this.errors = new Set()
    this.queue = []
    this.active = 0
  }
  load(events, retry = false) {
    if (retry) this.errors.clear()
    for (const event of events) {
      if (!event.event_id || !planDetailEvents.has(event.name)) continue
      if (this.details.has(event.event_id) || this.pending.has(event.event_id) || this.errors.has(event.event_id)) continue
      this.pending.add(event.event_id)
      this.queue.push(event)
    }
    this.pump()
    this.changed()
  }
  pump() {
    while (this.active < 4 && this.queue.length) {
      const event = this.queue.shift()
      const epoch = this.epoch
      this.active++
      Promise.resolve().then(() => event.category === 'run'
        ? this.api.runEvent(event.run_id, event.event_id)
        : this.api.scopeEvent(event.scope_id, event.event_id))
        .then(result => {
          if (!result.item) throw new Error('事件详情缺失')
          if (epoch === this.epoch) this.details.set(event.event_id, result.item)
        }).catch(() => {
          if (epoch === this.epoch) this.errors.add(event.event_id)
        }).finally(() => {
          if (epoch !== this.epoch) return
          this.active--
          this.pending.delete(event.event_id)
          this.pump()
          this.changed()
        })
    }
  }
}
