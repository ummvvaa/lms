import type { UsageClientEvent, UsageRegistry } from './types'

export type Delivery = 'sent' | 'retry' | 'discard'
export const USAGE_BUFFER_LIMIT = 1000
export const USAGE_SEND_TIMEOUT = 5000
type Send = (events: UsageClientEvent[], signal: AbortSignal, keepalive: boolean) => Promise<Delivery>

/** Одна отправка за раз; при неопределённом результате повторяются прежние UUID. */
export class UsageBuffer {
  private events: UsageClientEvent[] = []
  private request: AbortController | null = null
  private revision = 0
  private lastVisit: string | null = null
  private actions = new Set<string>()
  private screens = new Set<string>()
  private batchLimit = 100
  constructor(
    private send: Send,
    private active: () => boolean,
    private uuid: () => string = () => crypto.randomUUID(),
  ) {}

  configure(registry: Pick<UsageRegistry, 'client_actions' | 'client_screens' | 'batch_limit'>) {
    this.actions = new Set(registry.client_actions)
    this.screens = new Set(registry.client_screens)
    this.batchLimit = Math.max(1, Math.min(100, registry.batch_limit))
  }
  track(action: string, screen: string, visit?: string) {
    if (
      !this.active() ||
      !this.actions.has(action) ||
      !this.screens.has(screen) ||
      this.events.length >= USAGE_BUFFER_LIMIT
    )
      return
    if (visit !== undefined) {
      if (this.lastVisit === visit) return
      this.lastVisit = visit
    }
    this.events.push({ id: this.uuid(), action, screen })
  }
  reset() {
    this.revision += 1
    this.request?.abort()
    this.request = null
    this.events = []
    this.lastVisit = null
  }
  async flush(keepalive = false) {
    if (!this.active()) {
      this.reset()
      return
    }
    if (this.request || this.events.length === 0) return
    const batch = this.events.slice(0, this.batchLimit)
    const revision = this.revision
    const request = new AbortController()
    this.request = request
    let timeout: ReturnType<typeof setTimeout> | undefined
    try {
      const expired = new Promise<Delivery>((resolve) => {
        timeout = setTimeout(() => {
          request.abort()
          resolve('retry')
        }, USAGE_SEND_TIMEOUT)
      })
      const outcome = await Promise.race([this.send(batch, request.signal, keepalive), expired])
      if (revision !== this.revision || !this.active()) return
      if (outcome !== 'retry') {
        const delivered = new Set(batch.map((event) => event.id))
        this.events = this.events.filter((event) => !delivered.has(event.id))
      }
    } catch {
      // Сеть восстановится — следующая пачка сохранит UUID и не создаст дубли.
    } finally {
      clearTimeout(timeout)
      if (this.request === request) this.request = null
    }
  }
}
