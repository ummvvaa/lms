import type { CareerAnalysis } from '../../api/career'
import type { Tone } from '../../components/ui'

/** Цвет чипа состояния разбора: готов, не получился, отменён, идёт. */
export const analysisTone = (status: CareerAnalysis['status']): Tone =>
  status === 'done' ? 'good' : status === 'failed' ? 'bad' : status === 'cancelled' ? 'neutral' : 'warn'
