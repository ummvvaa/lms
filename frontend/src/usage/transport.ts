import { language } from '../i18n'
import type { Delivery } from './buffer'
import type { UsageClientEvent, UsageRegistry } from './types'

/** Фоновая аналитика не меняет состояние соединения основного приложения. */
export async function usageRegistry(signal?: AbortSignal): Promise<UsageRegistry> {
  const response = await fetch('/api/usage/registry/', {
    credentials: 'include',
    headers: { 'Accept-Language': language() },
    signal,
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<UsageRegistry>
}
/** Заголовок привязан к сессии при создании отправителя. Ротация cookie не меняет его владельца. */
export function createUsageSender() {
  const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? ''
  return async (events: UsageClientEvent[], signal: AbortSignal, keepalive: boolean): Promise<Delivery> => {
    const response = await fetch('/api/usage/', {
      method: 'POST',
      credentials: 'include',
      signal,
      keepalive,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': decodeURIComponent(token),
        'Accept-Language': language(),
      },
      body: JSON.stringify({ events }),
    })
    if (response.ok) return 'sent'
    return response.status >= 500 || [408, 429].includes(response.status) ? 'retry' : 'discard'
  }
}
