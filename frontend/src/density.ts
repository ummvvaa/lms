/**
 * Плотность интерфейса: атрибут `data-density` на <html>, числа — в
 * `styles/density.css`.
 *
 * Плотность задаёт роль, а не человек. Директор смотрит на 250 учеников
 * часами, и ему нужно, чтобы на экран влезало как можно больше строк.
 * Ученик заходит на пять минут к одному профилю и трём задачам — ему
 * нужен воздух. Это разные задачи, а не разные вкусы, поэтому
 * переключателя в профиле нет.
 */
import type { Role } from './api/types'

export type Density = 'dense' | 'roomy'

/** Плотность по роли. Ученику просторно, всем остальным плотно. */
export function densityFor(role: Role | undefined | null): Density {
  return role === 'student' ? 'roomy' : 'dense'
}

/** Применить плотность. Зовётся при загрузке профиля. */
export function applyDensity(next: Density) {
  document.documentElement.dataset.density = next
}
