/**
 * Навигация по ролям. Состав разделов взят из прототипа.
 * Экраны появляются в Фазе 3, здесь — только структура и заглушки.
 */
import type { Role } from '../api/types'

export interface NavItem {
  path: string
  label: string
  icon: string
}

const DIRECTOR_COMMON: NavItem[] = [
  { path: '/dashboard', label: 'Дашборд', icon: '◎' },
  { path: '/table', label: 'Таблица', icon: '⌗' },
]

export const NAV: Record<Role, NavItem[]> = {
  student: [
    { path: '/dashboard', label: 'Главная', icon: '◎' },
    { path: '/roadmap', label: 'Роадмап', icon: '▤' },
    { path: '/universities', label: 'Мои вузы', icon: '⌂' },
    { path: '/essays', label: 'Эссе', icon: '✎' },
    { path: '/alumni', label: 'Выпускники', icon: '◍' },
  ],
  director_behavior: [
    ...DIRECTOR_COMMON,
    { path: '/groups', label: 'Группы', icon: '▤' },
    { path: '/risks', label: 'Риски', icon: '!' },
  ],
  director_admission: [...DIRECTOR_COMMON, { path: '/deadlines', label: 'Дедлайны', icon: '⏱' }],
  director_exam: [...DIRECTOR_COMMON, { path: '/top30', label: 'TOP-30', icon: '★' }],
  director_talent: [...DIRECTOR_COMMON, { path: '/tracks', label: 'Треки', icon: '▤' }],
  director_sport: [...DIRECTOR_COMMON, { path: '/competitions', label: 'Соревнования', icon: '⏱' }],
  admin: [
    ...DIRECTOR_COMMON,
    { path: '/groups', label: 'Группы', icon: '▤' },
    { path: '/risks', label: 'Риски', icon: '!' },
    { path: '/overview', label: 'Сводный вид', icon: '◍' },
  ],
}

export function navFor(role: Role): NavItem[] {
  return NAV[role] ?? []
}
