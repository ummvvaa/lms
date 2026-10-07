import { afterEach, expect, it, vi } from 'vitest'
import { createUsageSender } from './transport'

vi.mock('../i18n', () => ({ language: () => 'ru' }))
afterEach(() => vi.unstubAllGlobals())

it('keeps the CSRF token captured for the owner when another login rotates the cookie', async () => {
  const cookie = { cookie: 'csrftoken=old-session' }
  vi.stubGlobal('document', cookie)
  const request = vi.fn().mockResolvedValue({ ok: false, status: 403 })
  vi.stubGlobal('fetch', request)
  const send = createUsageSender()
  cookie.cookie = 'csrftoken=new-session'
  const events = [{ id: 'event-1', action: 'filter.change', screen: '/dashboard' }]
  expect(await send(events, new AbortController().signal, false)).toBe('discard')
  expect(request.mock.calls[0][1].headers['X-CSRFToken']).toBe('old-session')
  expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ events })
})
