/** Тон и подпись статуса эссе — одно место для экрана эссе и главной. */
import type { Tone } from '../components/ui'

export const ESSAY_TONE: Record<string, Tone> = {
  draft: 'neutral',
  review: 'warn',
  revision: 'bad',
  done: 'good',
}

export const ESSAY_TITLE: Record<string, string> = {
  draft: 'Черновик',
  review: 'На проверке',
  revision: 'Правки',
  done: 'Готово',
}
