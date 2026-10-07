/** Подтверждение владельца: запоздалый ответ не возвращает уже сменившуюся сессию. */
import type { QueryClient } from '@tanstack/react-query'
import { ApiError, get } from '../api/client'
import type { Me } from '../api/types'
import { setUsageOwner, usageSessionChanging, usageSessionSnapshot } from '../usage/session'
import { claimTab } from './tabOwner'

export function sessionCredential() {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? ''
}

export function claimSession(queryClient: QueryClient, me: Me | null, credential = sessionCredential()) {
  if (me && claimTab(me.id))
    void queryClient.resetQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
  // Новая cookie той же учётки тоже создаёт новый буфер, но лишь после ответа /me.
  setUsageOwner(me?.id ?? null, credential)
  return me
}

export async function readSession(queryClient: QueryClient): Promise<Me | null> {
  const current = () => queryClient.getQueryData<Me | null>(['me']) ?? null
  for (let attempt = 0; attempt < 2; attempt += 1) {
    if (usageSessionChanging()) return current()
    const session = usageSessionSnapshot()
    const credential = sessionCredential()
    let me: Me | null
    try {
      me = await get<Me>('/auth/me/')
    } catch (error) {
      // Отказ — только 401/403. Обрыв связи не отменяет подтверждённую сессию.
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) me = null
      else throw error
    }
    // Не запускаем claimTab и не отдаём старый ответ в query-кэш.
    if (session !== usageSessionSnapshot()) return current()
    // В другой вкладке могли войти под той же учёткой без события owner.
    if (credential !== sessionCredential()) continue
    return claimSession(queryClient, me, credential)
  }
  return current()
}
