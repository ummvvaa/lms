import { QueryClient } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, get } from '../api/client'
import type { Me } from '../api/types'
import {
  beginUsageSessionChange,
  clearUsageSession,
  finishUsageSessionChange,
  usageOwner,
  usageSessionSnapshot,
} from '../usage/session'
import { claimSession, readSession } from './sessionRead'
import { claimTab } from './tabOwner'

vi.mock('../api/client', () => ({
  get: vi.fn(),
  ApiError: class extends Error {
    constructor(
      public status: number,
      public payload: unknown,
    ) {
      super(String(status))
    }
  },
}))
vi.mock('./tabOwner', () => ({ claimTab: vi.fn().mockReturnValue(false) }))
const first = { id: 1 } as Me
const second = { id: 2 } as Me
let client: QueryClient
let cookie: { cookie: string }
beforeEach(() => {
  vi.clearAllMocks()
  finishUsageSessionChange(null)
  clearUsageSession()
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  cookie = { cookie: 'csrftoken=initial' }
  vi.stubGlobal('document', cookie)
  claimSession(client, first)
  client.setQueryData(['me'], first)
  vi.mocked(claimTab).mockClear()
})
afterEach(() => {
  client.clear()
  vi.unstubAllGlobals()
  finishUsageSessionChange(null)
})

describe('confirmed auth session', () => {
  it.each(['success', 'expired'])('ignores a delayed old /me response after login: %s', async (outcome) => {
    let resolve!: (value: Me) => void
    let reject!: (reason: Error) => void
    vi.mocked(get).mockImplementationOnce(
      () =>
        new Promise((yes, no) => {
          resolve = yes
          reject = no
        }),
    )
    const pending = readSession(client)
    beginUsageSessionChange()
    finishUsageSessionChange(second.id)
    cookie.cookie = 'csrftoken=next'
    claimSession(client, second)
    client.setQueryData(['me'], second)
    vi.mocked(claimTab).mockClear()
    if (outcome === 'success') resolve(first)
    else reject(new ApiError(401, {}))
    expect(await pending).toEqual(second)
    expect(claimTab).not.toHaveBeenCalled()
    expect(usageOwner()).toBe(second.id)
  })
  it('does not read or claim an actor while login changes the cookie', async () => {
    beginUsageSessionChange()
    expect(await readSession(client)).toBe(first)
    expect(get).not.toHaveBeenCalled()
    expect(claimTab).not.toHaveBeenCalled()
    expect(usageOwner()).toBeNull()
  })
  it('renews the sender after a confirmed same-user login in another tab', async () => {
    const previous = usageSessionSnapshot()
    cookie.cookie = 'csrftoken=rotated'
    vi.mocked(get).mockResolvedValueOnce(first)
    expect(await readSession(client)).toBe(first)
    expect(usageOwner()).toBe(first.id)
    expect(usageSessionSnapshot()).not.toBe(previous)
  })
  it('rechecks the actor when a cookie rotates during /me without an owner event', async () => {
    let resolve!: (value: Me) => void
    vi.mocked(get)
      .mockImplementationOnce(
        () =>
          new Promise((yes) => {
            resolve = yes
          }),
      )
      .mockResolvedValueOnce(second)
    const pending = readSession(client)
    cookie.cookie = 'csrftoken=rotated'
    resolve(first)
    expect(await pending).toEqual(second)
    expect(get).toHaveBeenCalledTimes(2)
    expect(claimTab).toHaveBeenCalledExactlyOnceWith(second.id)
    expect(usageOwner()).toBe(second.id)
  })
  it('keeps the confirmed owner when the network fails', async () => {
    vi.mocked(get).mockRejectedValueOnce(new Error('offline'))
    await expect(readSession(client)).rejects.toThrow('offline')
    expect(usageOwner()).toBe(first.id)
    expect(claimTab).not.toHaveBeenCalled()
  })
})
