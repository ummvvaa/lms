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
 * Полтора десятка пунктов подряд читаются как список файлов. Наборы
 * у сотрудника и у ученика разные, потому что и работа разная:
 * у сотрудника «Работа» — то, что открывают каждый день, «Данные» —
 * справочники домена, «Настройки» — техническое у администратора;
 * у ученика «Основное» — он сам и его путь, «Поступление» — вузы,
 * деньги и план, «Работа» — то, что он делает руками (фаза 48).
 *
 * Порядок здесь и есть порядок групп на экране; пустая не рисуется.
 */
export type NavGroup = 'main' | 'admission' | 'work' | 'data' | 'settings'

export const NAV_GROUPS: { key: NavGroup; label: string }[] = [
  { key: 'main', label: 'Основное' },
  { key: 'admission', label: 'Поступление' },
  { key: 'work', label: 'Работа' },
  { key: 'data', label: 'Данные' },
  { key: 'settings', label: 'Настройки' },
]

export interface NavItem {
  path: string
  label: string
  icon: IconName
  group: NavGroup
  /** у раздела есть свои внутренние экраны — в меню это стрелка справа */
  nested?: boolean
  /** подпись в нижнем баре телефона: место там на одно слово (фаза 51).
   *  Задаётся только там, где сокращение очевидно и означает то же самое:
   *  «Мои вузы» — «Вузы». Переименовывать раздел нельзя — человек, который
   *  ходит и с ноутбука, станет искать в меню слово, которого там нет */
  short?: string
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
/** У ученика тот же раздел стоит в «Работе»: это то, что он читает, а не справочник. */
const RESOURCES_STUDENT: NavItem = { path: '/resources', label: 'Ресурсы', icon: 'openbook', group: 'work' }

export const NAV: Record<Role, NavItem[]> = {
  student: [
    // --- основное: он сам и его путь ---
    { path: '/dashboard', label: 'Главная', icon: 'dashboard', group: 'main' },
    // лестница пяти шагов: пока путь не пройден, она и есть главная,
    // а после — возвращается этим пунктом (фаза 37)
    { path: '/journey', label: 'Мой путь', icon: 'branch', group: 'main' },
    // календарь: экзамены, дедлайны, соревнования и задачи одним взглядом (фаза 39)
    { path: '/calendar', label: 'Календарь', icon: 'calendar', group: 'main' },
    // «Портфолио» — с фазы 38 ученик рассказывает о себе сам: баллы,
    // достижения, спорт, олимпиады, документы. Внутри осталось и всё,
    // что записала школа (бывший экран «Мои данные»)
    { path: '/my-data', label: 'Портфолио', icon: 'person', group: 'main', nested: true },
    // подбор с воронкой, стратегией и историей прогонов (фаза 40)
    { path: '/selection', label: 'Подбор вузов', icon: 'target', group: 'main' },

    // --- поступление: куда и на какие деньги ---
    { path: '/catalog', label: 'Каталог вузов', icon: 'search', group: 'admission' },
    { path: '/favorites', label: 'Избранное', icon: 'heart', group: 'admission' },
    { path: '/universities', label: 'Мои вузы', icon: 'bookmark', group: 'admission', short: 'Вузы' },
    // план по конкретному вузу — со своими задачами и дедлайном (фаза 41)
    { path: '/plan', label: 'План поступления', icon: 'checklist', group: 'admission' },
    // стипендии и гранты: свой раздел, а не строчка в каталоге вузов (фаза 44)
    { path: '/scholarships', label: 'Стипендии', icon: 'card', group: 'admission' },
    // профтест: анкета и разбор направлений (фаза 45)
    { path: '/career', label: 'Профтест', icon: 'bulb', group: 'admission' },

    // --- работа: то, что делается руками ---
    { path: '/essays', label: 'Эссе', icon: 'doc', group: 'work' },
    { path: '/prep', label: 'Подготовка', icon: 'pencil', group: 'work', nested: true },
    { path: '/roadmap', label: 'Роадмап', icon: 'layers', group: 'work' },
    // квиз без публичных рейтингов и достижения-бейджи (фаза 46)
    { path: '/quiz', label: 'Квиз', icon: 'medal', group: 'work' },
    { path: '/achievements', label: 'Достижения', icon: 'star', group: 'work' },
    RESOURCES_STUDENT,
  ],
  director_behavior: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    UPLOADS,
    RESOURCES,
    // анкету профтеста ведёт директор школы (фаза 45)
    { path: '/career-questions', label: 'Вопросы профтеста', icon: 'bulb', group: 'data' },
    // набор бейджей: условие — строка справочника, а не код (фаза 46)
    { path: '/badges', label: 'Достижения школы', icon: 'star', group: 'data' },
    // справочники фазы 49: из них живут карусель ученика и список обзвона
    { path: '/home-cues', label: 'Сюжеты главной', icon: 'bulb', group: 'data' },
    { path: '/call-rules', label: 'Правила обзвона', icon: 'person', group: 'data' },
    { path: '/groups', label: 'Группы', icon: 'people', group: 'data' },
    { path: '/contacts', label: 'Контакты родителей', icon: 'person', group: 'data', short: 'Контакты' },
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

/**
 * Четыре раздела нижнего бара телефона (фаза 51).
 *
 * Выбраны по частоте работы роли, а не по порядку меню: у ученика это
 * главная, внесение данных о себе, задачи и его список вузов; у пятерых
 * директоров — кабинет, очередь решений, таблица и один свой домен;
 * у администратора очереди подтверждений нет (подтверждать ему нечего),
 * поэтому вместо неё «Пользователи», а предложения он открывает на чтение.
 *
 * Пятая кнопка бара — «Ещё»: в ней всё остальное теми же группами,
 * что в меню. Список фильтруется по тому, что роли действительно
 * доступно: «Материалы» есть только у того, кому раздел открыт.
 */
export const TABS: Record<Role, string[]> = {
  student: ['/dashboard', '/my-data', '/roadmap', '/universities'],
  director_behavior: ['/dashboard', '/suggestions', '/table', '/contacts'],
  director_admission: ['/dashboard', '/suggestions', '/table', '/deadlines'],
  director_exam: ['/dashboard', '/suggestions', '/table', '/mocks'],
  director_talent: ['/dashboard', '/suggestions', '/table', '/materials'],
  director_sport: ['/dashboard', '/suggestions', '/table', '/competitions'],
  admin: ['/dashboard', '/users', '/table', '/suggestions'],
}

/**
 * Пункты нижнего бара: объявленная четвёрка, оставленная из того,
 * что роли доступно. Не набралось четырёх — добираем следующими
 * пунктами меню: пустое место в баре человеку ничего не объясняет.
 */
export function tabsFor(role: Role, items: NavItem[]): NavItem[] {
  const declared = (TABS[role] ?? [])
    .map((path) => items.find((item) => item.path === path))
    .filter((item): item is NavItem => item !== undefined)
  const rest = items.filter((item) => !declared.includes(item))
  return [...declared, ...rest].slice(0, 4)
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
  '/quiz',
  '/achievements',
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
  '/badges',
  '/home-cues',
  '/call-rules',
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
  '/badges': 'director_behavior',
  '/home-cues': 'director_behavior',
  '/call-rules': 'director_behavior',
}
