/**
 * Телефонная ширина (фаза 51).
 *
 * Число одно и живёт здесь: по нему перестраивается и разметка (в CSS
 * то же 640), и то, что нельзя сделать стилями — режимы календаря,
 * лист вместо выпадающего списка, карточки вместо таблицы.
 *
 * Два источника этого числа разъехались бы в первую же правку, поэтому
 * в CSS оно пишется как `@media (max-width: 640px)`, а здесь — как
 * `PHONE_WIDTH`, и обе стороны названы в одном комментарии.
 */
import { useEffect, useState } from 'react'

export const PHONE_WIDTH = 640

const QUERY = `(max-width: ${PHONE_WIDTH}px)`

/** Телефонная ширина сейчас? Перерисовывает экран при повороте. */
export function usePhone(): boolean {
  const [phone, setPhone] = useState(() => typeof window !== 'undefined' && window.matchMedia(QUERY).matches)

  useEffect(() => {
    const media = window.matchMedia(QUERY)
    const apply = () => setPhone(media.matches)
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [])

  return phone
}
