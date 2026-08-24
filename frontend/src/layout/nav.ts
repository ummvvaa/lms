/**
 * Навигация по ролям.
 *
 * Разделы директора — это секции его дашборда, а не отдельные экраны:
 * `anchor` говорит, к какому блоку прокрутиться. Пункт, ведущий на тот же
 * экран без якоря, — обман, поэтому такие здесь не заводим.
 */
import type { Role } from '../api/types'

export interface NavItem {
  path: string
  label: string
  icon: string
  /** id секции дашборда, к которой ведёт пункт */
  anchor?: string
}

const DIRECTOR_COMMON: NavItem[] = [
  { path: '/dashboard', label: 'Дашборд', icon: '◎' },
  { path: '/table', label: 'Таблица', icon: '⌗' },
  { path: '/import', label: 'Импорт', icon: '⇪' },
  { path: '/assistant', label: 'Помощник', icon: '✦' },
  { path: '/suggestions', label: 'Предложения', icon: '👁' },
  { path: '/digest', label: 'Дайджест', icon: '📰' },
  { path: '/alumni', label: 'Выпускники', icon: '◍' },
]

export const NAV: Record<Role, NavItem[]> = {
  student: [
    { path: '/dashboard', label: 'Главная', icon: '◎' },
    { path: '/roadmap', label: 'Роадмап', icon: '▤' },
    { path: '/universities', label: 'Мои вузы', icon: '⌂' },
    { path: '/catalog', label: 'Каталог вузов', icon: '🔎' },
    { path: '/prep', label: 'Подготовка', icon: '✎' },
    { path: '/essays', label: 'Эссе', icon: '✎' },
    { path: '/alumni', label: 'Выпускники', icon: '◍' },
  ],
  director_behavior: [
    ...DIRECTOR_COMMON,
    { path: '/groups', label: 'Группы', icon: '▤', anchor: 'groups' },
    { path: '/risks', label: 'Риски', icon: '!', anchor: 'risks' },
  ],
  director_admission: [
    ...DIRECTOR_COMMON,
    { path: '/directory', label: 'Справочник', icon: '🎓' },
    { path: '/deadlines', label: 'Дедлайны', icon: '⏱', anchor: 'deadlines' },
  ],
  director_exam: [
    ...DIRECTOR_COMMON,
    { path: '/top30', label: 'TOP-30', icon: '★', anchor: 'top30' },
    { path: '/mocks', label: 'Пробные', icon: '🎯', anchor: 'platform-mocks' },
  ],
  director_talent: [
    ...DIRECTOR_COMMON,
    { path: '/subjects', label: 'Предметы', icon: '📚' },
    { path: '/tracks', label: 'Треки', icon: '▤', anchor: 'tracks' },
  ],
  director_sport: [
    ...DIRECTOR_COMMON,
    { path: '/sport-types', label: 'Виды спорта', icon: '⚽️' },
    { path: '/competitions', label: 'Соревнования', icon: '⏱', anchor: 'competitions' },
  ],
  admin: [
    ...DIRECTOR_COMMON,
    { path: '/users', label: 'Пользователи', icon: '☰' },
    { path: '/archive', label: 'Архив', icon: '🗄' },
    { path: '/spend', label: 'Расходы на ИИ', icon: '💳' },
    { path: '/overview', label: 'Сводный вид', icon: '◍', anchor: 'overview' },
  ],
}

/** Что открыто человеку сверх его роли: считает сервер, не интерфейс. */
export interface NavExtras {
  /** раздел материалов — ученику его открывает олимпиадная группа */
  materials?: boolean
  /** ведёт олимпиадную группу и модерирует материалы */
  curator?: boolean
}

/** Пункты навигации роли. Флаг «видит всю школу» добавляет сводный вид. */
export function navFor(role: Role, seesWholeSchool = false, extras: NavExtras = {}): NavItem[] {
  let items = NAV[role] ?? []
  if (seesWholeSchool && role !== 'admin' && !items.some((i) => i.path === '/overview')) {
    items = [...items, { path: '/overview', label: 'Сводный вид', icon: '◍', anchor: 'overview' }]
  }
  // пункт «Материалы» появляется только у тех, кому раздел открыт:
  // ученик вне олимпиадной группы не должен даже знать, что он есть
  if (extras.materials) {
    items = [...items, { path: '/materials', label: 'Материалы', icon: '📚' }]
  }
  if (extras.curator) {
    items = [...items, { path: '/olympiad-group', label: 'Олимпиадная группа', icon: '🏅' }]
  }
  return items
}

/** Якорь секции для маршрута — им пользуется дашборд, чтобы прокрутиться. */
export function anchorFor(role: Role, path: string): string | undefined {
  return navFor(role, true).find((item) => item.path === path)?.anchor
}

/** Экраны ученика — сотруднику там нечего показывать: карточки ученика у него нет. */
export const STUDENT_ONLY = ['/roadmap', '/universities', '/essays', '/catalog', '/onboarding', '/prep']

/** Экраны сотрудников — ученику закрыты. */
export const STAFF_ONLY = [
  '/users',
  '/directory',
  '/archive',
  '/table',
  '/import',
  '/assistant',
  '/suggestions',
  '/digest',
  '/groups',
  '/risks',
  '/overview',
  '/deadlines',
  '/top30',
  '/mocks',
  '/tracks',
  '/competitions',
  '/subjects',
  '/sport-types',
  '/olympiad-group',
  '/spend',
]
