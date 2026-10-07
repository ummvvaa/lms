import { afterEach, describe, expect, it, vi } from 'vitest'
import { UsageBuffer, USAGE_BUFFER_LIMIT, USAGE_SEND_TIMEOUT, type Delivery } from './buffer'
import {
  beginUsageSessionChange,
  finishUsageSessionChange,
  subscribeUsageSession,
  usageOwner,
} from './session'
import type { UsageClientEvent } from './types'

const policy = {
  client_actions: ['screen.open', 'tab.change', 'filter.change'],
  client_screens: ['/dashboard', '/students/:id'],
  batch_limit: 100,
}
function buffer(
  send: (events: UsageClientEvent[], signal: AbortSignal, keepalive: boolean) => Promise<Delivery>,
  active = () => true,
) {
  let id = 0
  const queue = new UsageBuffer(send, active, () => `event-${++id}`)
  queue.configure(policy)
  return queue
}
afterEach(() => {
  vi.useRealTimers()
  finishUsageSessionChange(null)
})

describe('usage delivery', () => {
  it('retries the same UUIDs after an uncertain response and acknowledges only the delivered batch', async () => {
    const send = vi.fn().mockResolvedValueOnce('retry').mockResolvedValue('sent')
    const queue = buffer(send)
    queue.track('filter.change', '/dashboard')
    await queue.flush()
    queue.track('tab.change', '/dashboard')
    await queue.flush()
    expect(send.mock.calls[1][0][0]).toEqual(send.mock.calls[0][0][0])
    expect(send.mock.calls[1][0]).toHaveLength(2)
    await queue.flush()
    expect(send).toHaveBeenCalledTimes(2)
  })
  it('bounds an offline queue and sends batches of at most 100', async () => {
    const send = vi.fn().mockResolvedValue('sent')
    const queue = buffer(send)
    for (let index = 0; index < USAGE_BUFFER_LIMIT + 20; index += 1)
      queue.track('filter.change', '/dashboard')
    for (let index = 0; index < 12; index += 1) await queue.flush()
    expect(send).toHaveBeenCalledTimes(10)
    expect(send.mock.calls.flatMap((call) => call[0])).toHaveLength(USAGE_BUFFER_LIMIT)
    expect(send.mock.calls.every((call) => call[0].length <= 100)).toBe(true)
  })
  it('aborts a stalled request after five seconds and retries its UUID', async () => {
    vi.useFakeTimers()
    const send = vi
      .fn()
      .mockImplementationOnce(() => new Promise(() => {}))
      .mockResolvedValue('sent')
    const queue = buffer(send)
    queue.track('filter.change', '/dashboard')
    const stalled = queue.flush()
    await vi.advanceTimersByTimeAsync(USAGE_SEND_TIMEOUT)
    await stalled
    expect(send.mock.calls[0][1].aborted).toBe(true)
    await queue.flush()
    expect(send.mock.calls[1][0]).toEqual(send.mock.calls[0][0])
  })
  it('does not duplicate an open screen or admit server actions, raw paths, or filter data', async () => {
    const send = vi.fn().mockResolvedValue('sent')
    const queue = buffer(send)
    queue.track('screen.open', '/students/:id', '/students/51')
    queue.track('screen.open', '/students/:id', '/students/51')
    queue.track('screen.open', '/students/:id', '/students/52')
    queue.track('journal.grade.set', '/dashboard')
    queue.track('filter.change', '/students/52?name=private')
    await queue.flush()
    expect(send.mock.calls[0][0]).toEqual([
      { id: 'event-1', action: 'screen.open', screen: '/students/:id' },
      { id: 'event-2', action: 'screen.open', screen: '/students/:id' },
    ])
  })
  it('clears the old user before a cookie changes and never sends their events as the new user', async () => {
    finishUsageSessionChange(1)
    const send = vi.fn().mockResolvedValue('sent')
    const queue = buffer(send, () => usageOwner() === 1)
    const unsubscribe = subscribeUsageSession(() => queue.reset())
    queue.track('filter.change', '/dashboard')
    beginUsageSessionChange()
    queue.track('tab.change', '/dashboard')
    await queue.flush()
    finishUsageSessionChange(2)
    await queue.flush()
    expect(send).not.toHaveBeenCalled()
    const next = buffer(send, () => usageOwner() === 2)
    next.track('tab.change', '/dashboard')
    await next.flush()
    expect(send.mock.calls[0][0]).toEqual([{ id: 'event-1', action: 'tab.change', screen: '/dashboard' }])
    unsubscribe()
  })
  it('does not let the completion of an old request clear a new session buffer', async () => {
    let finish!: (value: Delivery) => void
    const send = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Delivery>((resolve) => {
            finish = resolve
          }),
      )
      .mockResolvedValue('sent')
    const queue = buffer(send)
    queue.track('filter.change', '/dashboard')
    const old = queue.flush()
    queue.reset()
    queue.track('tab.change', '/dashboard')
    finish('sent')
    await old
    await queue.flush()
    expect(send.mock.calls[1][0]).toEqual([{ id: 'event-2', action: 'tab.change', screen: '/dashboard' }])
  })
})
