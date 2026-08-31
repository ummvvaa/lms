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

/**
 * Группа пункта в боковом меню.
 *
 * Одиннадцать пунктов подряд читаются как список файлов. «Работа» —
 * то, что открывают каждый день; «Данные» — справочники и разделы
 * домена; «Настройки» — техническое, у администратора.
 */
export type NavGroup = 'work' | 'data' | 'settings'

export const NAV_GROUPS: { key: NavGroup; label: string }[] = [
  { key: 'work', label: 'Работа' },
  { key: 'data', label: 'Данные' },
  { key: 'settings', label: 'Настройки' },
]

export interface NavItem {
  path: string
  label: string
  icon: IconName
  group: NavGroup
}

const DIRECTOR_COMMON: NavItem[] = [
  { path: '/dashboard', label: 'Дашборд', icon: 'dashboard', group: 'work' },
  { path: '/table', label: 'Таблица', icon: 'table', group: 'work' },
  { path: '/assistant', label: 'Помощник', icon: 'sparkle', group: 'work' },
  { path: '/suggestions', label: 'Предложения', icon: 'bulb', group: 'work' },
  { path: '/digest', label: 'Дайджест', icon: 'news', group: 'work' },
]

/**
 * Файлы грузит только администратор (фаза 35): у него пункт «Импорт».
 * Директор на том же адресе видит историю загрузок по своему домену —
 * что залил администратор и что можно отменить, — и подсказку, что данные
 * вносятся руками или вставкой текста. Пункта «Импорт» у него нет.
 */
const IMPORT: NavItem = { path: '/import', label: 'Импорт', icon: 'upload', group: 'work' }
const UPLOADS: NavItem = { path: '/import', label: 'История загрузок', icon: 'clock', group: 'data' }

/** Шаблоны задач ведут пять директоров: владельца-домена у задач нет,
 *  но и администратору там делать нечего — план потока не его хозяйство. */
const TEMPLATES: NavItem = {
  path: '/task-templates',
  label: 'Шаблоны задач',
  icon: 'checklist',
  group: 'data',
}

export const NAV: Record<Role, NavItem[]> = {
  student: [
    { path: '/dashboard', label: 'Главная', icon: 'dashboard', group: 'work' },
    // лестница пяти шагов: пока путь не пройден, она и есть главная,
    // а после — возвращается этим пунктом (фаза 37)
    { path: '/journey', label: 'Мой путь', icon: 'branch', group: 'work' },
    // «Мои данные» — ответ на вопрос «а что про меня записали».
    // До фазы 30 ученик своих баллов не видел вовсе: кабинет показывал
    // только процент готовности и задачи
    { path: '/my-data', label: 'Мои данные', icon: 'person', group: 'data' },
    { path: '/roadmap', label: 'Роадмап', icon: 'checklist', group: 'work' },
    { path: '/universities', label: 'Мои вузы', icon: 'bookmark', group: 'work' },
    { path: '/catalog', label: 'Каталог вузов', icon: 'search', group: 'work' },
    { path: '/prep', label: 'Подготовка', icon: 'pencil', group: 'work' },
    { path: '/essays', label: 'Эссе', icon: 'doc', group: 'work' },
  ],
  director_behavior: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    { path: '/groups', label: 'Группы', icon: 'people', group: 'data' },
    { path: '/contacts', label: 'Контакты родителей', icon: 'person', group: 'data' },
    { path: '/risks', label: 'Риски', icon: 'alert', group: 'data' },
  ],
  director_admission: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    { path: '/directory', label: 'Справочник', icon: 'building', group: 'data' },
    { path: '/deadlines', label: 'Дедлайны', icon: 'clock', group: 'data' },
  ],
  director_exam: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    { path: '/top30', label: 'TOP-30', icon: 'star', group: 'data' },
    { path: '/mocks', label: 'Пробные', icon: 'target', group: 'data' },
  ],
  director_talent: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    { path: '/subjects', label: 'Предметы', icon: 'book', group: 'data' },
    { path: '/tracks', label: 'Треки', icon: 'branch', group: 'data' },
  ],
  director_sport: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    { path: '/sport-types', label: 'Виды спорта', icon: 'trophy', group: 'data' },
    { path: '/competitions', label: 'Соревнования', icon: 'calendar', group: 'data' },
  ],
  // у администратора дашборд и есть сводный вид — отдельного пункта
  // «Сводный вид» ему не заводим, он вёл бы на тот же экран
  admin: [
    ...DIRECTOR_COMMON,
    IMPORT,
    { path: '/users', label: 'Пользователи', icon: 'person', group: 'settings' },
    { path: '/archive', label: 'Архив', icon: 'box', group: 'settings' },
    { path: '/spend', label: 'Расходы на ИИ', icon: 'card', group: 'settings' },
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
    items = [...items, { path: '/overview', label: 'Сводный вид', icon: 'layers', group: 'data' }]
  }
  // пункт «Материалы» появляется только у тех, кому раздел открыт:
  // остальным директорам его не показываем вовсе — там портфолио
  // олимпиадников, и ведёт его директор талантов
  if (extras.materials) {
    items = [...items, { path: '/materials', label: 'Материалы', icon: 'openbook', group: 'data' }]
  }
  if (extras.curator) {
    items = [...items, { path: '/olympiad-group', label: 'Олимпиадная группа', icon: 'medal', group: 'data' }]
  }
  return items
}

/** Экраны ученика — сотруднику там нечего показывать: карточки ученика у него нет. */
export const STUDENT_ONLY = [
  '/roadmap',
  '/universities',
  '/essays',
  '/catalog',
  '/onboarding',
  '/prep',
  '/my-data',
  '/journey',
]

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
  '/contacts',
  '/task-templates',
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
  '/contacts': 'director_behavior',
  '/risks': 'director_behavior',
  '/deadlines': 'director_admission',
  '/top30': 'director_exam',
  '/mocks': 'director_exam',
  '/tracks': 'director_talent',
  '/competitions': 'director_sport',
}
