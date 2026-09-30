/** Тон и подпись статуса эссе — одно место для экрана эссе и главной.
 *  Подписи — ключи перевода: показываются через `t()`. */
import type { Tone } from '../components/ui'
import { tk } from '../i18n'

export const ESSAY_TONE: Record<string, Tone> = {
  draft: 'neutral',
  review: 'warn',
  revision: 'bad',
  done: 'good',
}

export const ESSAY_TITLE: Record<string, string> = {
  draft: tk('Черновик'),
  review: tk('На проверке'),
  revision: tk('Правки'),
  done: tk('Готово'),
}
