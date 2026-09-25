/**
 * Телефонная ширина.
 *
 * Число одно и живёт здесь: по нему перестраивается и разметка (в CSS
 * то же 759), и то, что нельзя сделать стилями — режимы календаря,
 * лист вместо выпадающего списка, карточки вместо таблицы. Телефон —
 * всё, что уже 760: на 641–759 после меню в 228 контенту оставалось бы
 * меньше 530.
 *
 * Два источника этого числа разъехались бы в первую же правку, поэтому
 * в CSS оно пишется как `@media (max-width: 759px)`, а здесь — как
 * `PHONE_WIDTH`, и обе стороны названы в одном комментарии.
 */
import { useEffect, useState } from 'react'

export const PHONE_WIDTH = 759

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
