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

/** Ресурсы школы (фаза 45): читают все, ведут пять директоров вместе —
 *  владельца-домена у раздела нет, и пункт стоит у каждого. */
const RESOURCES: NavItem = { path: '/resources', label: 'Ресурсы', icon: 'openbook', group: 'data' }

export const NAV: Record<Role, NavItem[]> = {
  student: [
    { path: '/dashboard', label: 'Главная', icon: 'dashboard', group: 'work' },
    // лестница пяти шагов: пока путь не пройден, она и есть главная,
    // а после — возвращается этим пунктом (фаза 37)
    { path: '/journey', label: 'Мой путь', icon: 'branch', group: 'work' },
    // календарь: экзамены, дедлайны, соревнования и задачи одним взглядом (фаза 39)
    { path: '/calendar', label: 'Календарь', icon: 'calendar', group: 'work' },
    // «Портфолио» — с фазы 38 ученик рассказывает о себе сам: баллы,
    // достижения, спорт, олимпиады, документы. Внутри осталось и всё,
    // что записала школа (бывший экран «Мои данные»)
    { path: '/my-data', label: 'Портфолио', icon: 'person', group: 'data' },
    { path: '/roadmap', label: 'Роадмап', icon: 'checklist', group: 'work' },
    // план по конкретному вузу — со своими задачами и дедлайном (фаза 41)
    { path: '/plan', label: 'План поступления', icon: 'target', group: 'work' },
    { path: '/universities', label: 'Мои вузы', icon: 'bookmark', group: 'work' },
    // подбор с воронкой, стратегией и историей прогонов (фаза 40)
    { path: '/selection', label: 'Подбор вузов', icon: 'target', group: 'work' },
    { path: '/catalog', label: 'Каталог вузов', icon: 'search', group: 'work' },
    { path: '/favorites', label: 'Избранное', icon: 'heart', group: 'work' },
    // стипендии и гранты: свой раздел, а не строчка в каталоге вузов (фаза 44)
    { path: '/scholarships', label: 'Стипендии', icon: 'card', group: 'work' },
    // профтест: анкета и разбор направлений (фаза 45)
    { path: '/career', label: 'Профтест', icon: 'bulb', group: 'work' },
    { path: '/prep', label: 'Подготовка', icon: 'pencil', group: 'work' },
    { path: '/essays', label: 'Эссе', icon: 'doc', group: 'work' },
    RESOURCES,
  ],
  director_behavior: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    RESOURCES,
    // анкету профтеста ведёт директор школы (фаза 45)
    { path: '/career-questions', label: 'Вопросы профтеста', icon: 'bulb', group: 'data' },
    { path: '/groups', label: 'Группы', icon: 'people', group: 'data' },
    { path: '/contacts', label: 'Контакты родителей', icon: 'person', group: 'data' },
    { path: '/risks', label: 'Риски', icon: 'alert', group: 'data' },
  ],
  director_admission: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    RESOURCES,
    { path: '/directory', label: 'Справочник', icon: 'building', group: 'data' },
    { path: '/deadlines', label: 'Дедлайны', icon: 'clock', group: 'data' },
    // конструктор эссе: типы, гайды, проверка, примеры (фаза 43)
    { path: '/essay-content', label: 'Конструктор эссе', icon: 'doc', group: 'data' },
    // справочник стипендий: ведёт он же, ученик видит его у себя (фаза 44)
    { path: '/scholarship-directory', label: 'Стипендии', icon: 'card', group: 'data' },
  ],
  director_exam: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    RESOURCES,
    { path: '/top30', label: 'TOP-30', icon: 'star', group: 'data' },
    { path: '/mocks', label: 'Пробные', icon: 'target', group: 'data' },
    // справочник экзаменов: из него ученик выбирает экзамен для цели (фаза 39)
    { path: '/exam-kinds', label: 'Экзамены', icon: 'book', group: 'data' },
  ],
  director_talent: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    RESOURCES,
    { path: '/subjects', label: 'Предметы', icon: 'book', group: 'data' },
    { path: '/tracks', label: 'Треки', icon: 'branch', group: 'data' },
  ],
  director_sport: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    RESOURCES,
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
  '/calendar',
  '/selection',
  '/favorites',
  '/plan',
  '/scholarships',
  '/career',
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
  '/exam-kinds',
  '/essay-content',
  '/scholarship-directory',
  '/career-questions',
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
  '/exam-kinds': 'director_exam',
  '/tracks': 'director_talent',
  '/competitions': 'director_sport',
  '/essay-content': 'director_admission',
  '/scholarship-directory': 'director_admission',
  '/career-questions': 'director_behavior',
}
