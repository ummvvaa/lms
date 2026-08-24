/**
 * Навигация по ролям.
 *
 * Пункт меню — это отдельный экран со своим адресом. Прокрутки к секции
 * длинного дашборда больше нет: раздел, до которого надо доскроллить,
 * человек не считает разделом, а адрес такого пункта нечем открыть
 * в новой вкладке и некому отправить.
 */
import type { IconName } from './icons'
import type { Role } from '../api/types'

export interface NavItem {
  path: string
  label: string
  icon: IconName
}

const DIRECTOR_COMMON: NavItem[] = [
  { path: '/dashboard', label: 'Дашборд', icon: 'dashboard' },
  { path: '/table', label: 'Таблица', icon: 'table' },
  { path: '/import', label: 'Импорт', icon: 'upload' },
  { path: '/assistant', label: 'Помощник', icon: 'sparkle' },
  { path: '/suggestions', label: 'Предложения', icon: 'bulb' },
  { path: '/digest', label: 'Дайджест', icon: 'news' },
  { path: '/alumni', label: 'Выпускники', icon: 'cap' },
]

export const NAV: Record<Role, NavItem[]> = {
  student: [
    { path: '/dashboard', label: 'Главная', icon: 'dashboard' },
    { path: '/roadmap', label: 'Роадмап', icon: 'checklist' },
    { path: '/universities', label: 'Мои вузы', icon: 'bookmark' },
    { path: '/catalog', label: 'Каталог вузов', icon: 'search' },
    { path: '/prep', label: 'Подготовка', icon: 'pencil' },
    { path: '/essays', label: 'Эссе', icon: 'doc' },
    { path: '/alumni', label: 'Выпускники', icon: 'cap' },
  ],
  director_behavior: [
    ...DIRECTOR_COMMON,
    { path: '/groups', label: 'Группы', icon: 'people' },
    { path: '/risks', label: 'Риски', icon: 'alert' },
  ],
  director_admission: [
    ...DIRECTOR_COMMON,
    { path: '/directory', label: 'Справочник', icon: 'building' },
    { path: '/deadlines', label: 'Дедлайны', icon: 'clock' },
  ],
  director_exam: [
    ...DIRECTOR_COMMON,
    { path: '/top30', label: 'TOP-30', icon: 'star' },
    { path: '/mocks', label: 'Пробные', icon: 'target' },
  ],
  director_talent: [
    ...DIRECTOR_COMMON,
    { path: '/subjects', label: 'Предметы', icon: 'book' },
    { path: '/tracks', label: 'Треки', icon: 'branch' },
  ],
  director_sport: [
    ...DIRECTOR_COMMON,
    { path: '/sport-types', label: 'Виды спорта', icon: 'trophy' },
    { path: '/competitions', label: 'Соревнования', icon: 'calendar' },
  ],
  // у администратора дашборд и есть сводный вид — отдельного пункта
  // «Сводный вид» ему не заводим, он вёл бы на тот же экран
  admin: [
    ...DIRECTOR_COMMON,
    { path: '/users', label: 'Пользователи', icon: 'person' },
    { path: '/archive', label: 'Архив', icon: 'box' },
    { path: '/spend', label: 'Расходы на ИИ', icon: 'card' },
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
    items = [...items, { path: '/overview', label: 'Сводный вид', icon: 'layers' }]
  }
  // пункт «Материалы» появляется только у тех, кому раздел открыт:
  // остальным директорам его не показываем вовсе — там портфолио
  // олимпиадников, и ведёт его директор талантов
  if (extras.materials) {
    items = [...items, { path: '/materials', label: 'Материалы', icon: 'openbook' }]
  }
  if (extras.curator) {
    items = [...items, { path: '/olympiad-group', label: 'Олимпиадная группа', icon: 'medal' }]
  }
  return items
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

/**
 * Разделы, которые ведёт один домен.
 *
 * Пункт меню у чужой роли не показывается, а прямой адрес отбивается
 * в `Protected`: пункта нет — значит и экрана быть не должно.
 */
export const DOMAIN_ONLY: Record<string, Role> = {
  '/groups': 'director_behavior',
  '/risks': 'director_behavior',
  '/deadlines': 'director_admission',
  '/top30': 'director_exam',
  '/mocks': 'director_exam',
  '/tracks': 'director_talent',
  '/competitions': 'director_sport',
}
