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
import { tk } from '../i18n'

/**
 * Группа пункта в боковом меню.
 *
 * Полтора десятка пунктов подряд читаются как список файлов. Наборы
 * у сотрудника и у ученика разные, потому что и работа разная:
 * у сотрудника «Работа» — то, что открывают каждый день, «Учёба» —
 * расписание, оценки и журналы, «Данные» — справочники домена,
 * «Настройки» — техническое у администратора, «Ещё» — то, что куратор
 * открывает редко; у ученика «Основное» — он сам и его путь,
 * «Достижения» — олимпиады и спорт у 8–10, «Поступление» — вузы, деньги
 * и план, «Работа» — то, что он делает руками.
 *
 * Порядок здесь и есть порядок групп на экране; пустая не рисуется.
 */
export type NavGroup = 'main' | 'achievements' | 'admission' | 'work' | 'academics' | 'data' | 'settings' | 'more'

export const NAV_GROUPS: { key: NavGroup; label: string }[] = [
  { key: 'main', label: tk('Основное') },
  { key: 'achievements', label: tk('Достижения') },
  { key: 'admission', label: tk('Поступление') },
  { key: 'work', label: tk('Работа') },
  { key: 'academics', label: tk('Учёба') },
  { key: 'data', label: tk('Данные') },
  { key: 'settings', label: tk('Настройки') },
  { key: 'more', label: tk('Ещё') },
]

export interface NavItem {
  path: string
  label: string
  icon: IconName
  group: NavGroup
  /** у раздела есть свои внутренние экраны — в меню это стрелка справа */
  nested?: boolean
  /** подпись в нижнем баре телефона: место там на одно слово.
   *  Задаётся только там, где сокращение очевидно и означает то же самое:
   *  «Мои вузы» — «Вузы». Переименовывать раздел нельзя — человек, который
   *  ходит и с ноутбука, станет искать в меню слово, которого там нет */
  short?: string
}

const DIRECTOR_COMMON: NavItem[] = [
  { path: '/dashboard', label: tk('Дашборд'), icon: 'home', group: 'work' },
  { path: '/table', label: tk('Таблица'), icon: 'table', group: 'work' },
  { path: '/assistant', label: tk('Помощник'), icon: 'sparkle', group: 'work' },
  { path: '/suggestions', label: tk('Предложения'), icon: 'bulb', group: 'work' },
  { path: '/digest', label: tk('Дайджест'), icon: 'news', group: 'work' },
]

/**
 * «Учёба» у Кымбат и администратора: расписание с правкой уроков, подгруппы
 * и потоки, учителя, успеваемость по школе, учебный год (четверти, звонки,
 * шкала, отчёты родителям). У куратора своя «Учёба» — расписание групп,
 * успеваемость и отчёты родителям; посещаемость по урокам стоит в «Работе».
 */
export const ACADEMICS: NavItem[] = [
  { path: '/schedule', label: tk('Расписание'), icon: 'schedule', group: 'academics' },
  { path: '/cohorts', label: tk('Подгруппы и потоки'), icon: 'layers', group: 'academics', short: tk('Составы') },
  { path: '/teachers', label: tk('Учителя'), icon: 'idcard', group: 'academics' },
  { path: '/grades', label: tk('Успеваемость'), icon: 'chart', group: 'academics' },
  { path: '/reports', label: tk('Отчёты родителям'), icon: 'report', group: 'academics', short: tk('Отчёты') },
  { path: '/academic-year', label: tk('Учебный год'), icon: 'year', group: 'academics', short: tk('Год') },
  // сдача ДЗ: Кымбат и администратор видят задания со сдачей всей школы
  { path: '/homework-review', label: tk('Проверка ДЗ'), icon: 'homework', group: 'academics', short: tk('ДЗ') },
]

/** «Учёба» куратора — придёт со своими экранами. */
export const ACADEMICS_CURATOR: NavItem[] = [
  { path: '/schedule', label: tk('Расписание'), icon: 'schedule', group: 'academics' },
  { path: '/grades', label: tk('Успеваемость'), icon: 'chart', group: 'academics' },
  { path: '/reports', label: tk('Отчёты родителям'), icon: 'report', group: 'academics', short: tk('Отчёты') },
]

/**
 * «Импорт» — у администратора и у Кымбат: остальные директора и кураторы
 * вносят руками (решение владельца после разбора кабинетов). Мастер один
 * на все домены, Кымбат видит в нём чужие колонки помеченными «домен
 * не ваш, будет пропущен». Тот же список держит сервер
 * (`import_registry.WIZARD_ROLES`).
 */
const IMPORT: NavItem = { path: '/import', label: tk('Импорт'), icon: 'upload', group: 'work' }

/** Шаблоны задач ведут пять директоров: владельца-домена у задач нет,
 *  но и администратору там делать нечего — план потока не его хозяйство. */
const TEMPLATES: NavItem = {
  path: '/task-templates',
  label: tk('Шаблоны задач'),
  icon: 'checklist',
  group: 'data',
}

/** Ресурсы школы (фаза 45): читают все, ведут пять директоров вместе —
 *  владельца-домена у раздела нет, и пункт стоит у каждого. */
const RESOURCES: NavItem = { path: '/resources', label: tk('Ресурсы'), icon: 'openbook', group: 'data' }

/** Проверка ДЗ со сдачей в LMS (30.09.2026): у учителя и у того, кто ведёт уроки при другой роли. */
const HOMEWORK_REVIEW: NavItem = { path: '/homework-review', label: tk('Проверка ДЗ'), icon: 'homework', group: 'work', short: tk('ДЗ') }

/**
 * Кому открыта «Проверка ДЗ»: учителю, Кымбат и администратору (им — вся
 * школа) и сотруднику, который ведёт уроки, включая куратора. Сервер
 * ограничивает проверку его уроками (`homework.services.may_check`).
 */
export function homeworkReviewOpen(role: Role, teaches = false): boolean {
  if (['teacher', 'director_exam', 'admin'].includes(role)) return true
  return teaches && role !== 'student'
}

/** Аналитика использования доступна администратору и директору школы. */
export function usageOpen(role: Role): boolean {
  return role === 'admin' || role === 'director_behavior'
}
const USAGE: NavItem = { path: '/usage', label: tk('Использование'), icon: 'usage', group: 'data' }

export const NAV: Record<Role, NavItem[]> = {
  student: [
    // --- основное: он сам и его путь ---
    { path: '/dashboard', label: tk('Главная'), icon: 'home', group: 'main' },
    // учебная часть: своя неделя уроков и свои оценки по предметам
    { path: '/schedule', label: tk('Расписание'), icon: 'schedule', group: 'main' },
    { path: '/grades', label: tk('Оценки'), icon: 'book', group: 'main' },
    // сдача ДЗ в LMS: к сдаче, на проверке, проверено — у всех параллелей
    { path: '/homework', label: tk('Домашние задания'), icon: 'homework', group: 'main', short: tk('ДЗ') },
    // календарь: экзамены, дедлайны, соревнования и задачи одним взглядом (фаза 39)
    { path: '/calendar', label: tk('Календарь'), icon: 'calendar', group: 'main' },
    // «Портфолио» — с фазы 38 ученик рассказывает о себе сам: баллы,
    // достижения, спорт, олимпиады, документы. Внутри осталось и всё,
    // что записала школа (бывший экран «Мои данные»)
    { path: '/my-data', label: tk('Портфолио'), icon: 'person', group: 'main', nested: true },
    // подбор с воронкой, стратегией и историей прогонов (фаза 40)
    { path: '/selection', label: tk('Подбор вузов'), icon: 'target', group: 'main' },

    // --- достижения 8–10: у 11 это вкладки «Портфолио», кабинет не меняется ---
    { path: '/olympiads', label: tk('Олимпиады'), icon: 'medal', group: 'achievements' },
    { path: '/sport', label: tk('Спорт'), icon: 'ball', group: 'achievements' },

    // --- поступление: куда и на какие деньги ---
    // «Мои вузы» — вкладка каталога (решение владельца, 07.10.2026)
    { path: '/catalog', label: tk('Каталог вузов'), icon: 'search', group: 'admission', short: tk('Вузы') },
    // профтест: анкета и разбор направлений (фаза 45)
    { path: '/career', label: tk('Профтест'), icon: 'compass', group: 'admission' },

    // --- работа: то, что делается руками ---
    { path: '/essays', label: tk('Эссе'), icon: 'doc', group: 'work' },
    { path: '/prep', label: tk('Подготовка'), icon: 'pencil', group: 'work', nested: true },
    // достижения-бейджи
    { path: '/achievements', label: tk('Достижения'), icon: 'star', group: 'work' },
  ],
  director_behavior: [
    USAGE,
    ...DIRECTOR_COMMON,
    TEMPLATES,
    RESOURCES,
    // правила обзвона (фаза 49): из них живёт список «кому позвонить»
    { path: '/call-rules', label: tk('Правила обзвона'), icon: 'list', group: 'data' },
    // посещаемость по дням (фаза 66): тот же экран, что у куратора,
    // только без границы групп — школа целиком
    { path: '/attendance', label: tk('Посещаемость'), icon: 'presence', group: 'work' },
    // отчёты родителям по всем группам (решение владельца, 27.09.2026)
    { path: '/reports', label: tk('Отчёты родителям'), icon: 'report', group: 'work', short: tk('Отчёты') },
    { path: '/groups', label: tk('Группы'), icon: 'people', group: 'data' },
    { path: '/contacts', label: tk('Контакты родителей'), icon: 'phone', group: 'data', short: tk('Контакты') },
    { path: '/risks', label: tk('Риски'), icon: 'alert', group: 'data' },
  ],
  director_admission: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    RESOURCES,
    { path: '/directory', label: tk('Справочник'), icon: 'building', group: 'data' },
    { path: '/deadlines', label: tk('Дедлайны'), icon: 'clock', group: 'data' },
    // конструктор эссе: типы, гайды, проверка, примеры (фаза 43)
    { path: '/essay-content', label: tk('Конструктор эссе'), icon: 'doc', group: 'data' },
    // справочник стипендий: ведёт он же, ученик видит его у себя (фаза 44)
    { path: '/scholarship-directory', label: tk('Стипендии'), icon: 'card', group: 'data' },
    // анкета профтеста — про выбор направления, её ведёт Асем
    { path: '/career-questions', label: tk('Вопросы профтеста'), icon: 'compass', group: 'data' },
  ],
  director_exam: [
    ...DIRECTOR_COMMON,
    IMPORT,
    ...ACADEMICS,
    TEMPLATES,
    RESOURCES,
    { path: '/top30', label: tk('ТОП-30'), icon: 'star', group: 'data' },
    { path: '/mocks', label: tk('Mock Test онлайн'), icon: 'stopwatch', group: 'data', short: tk('Mock Test') },
    // пробники школы файлом от учителя — не то же, что пробные платформы (фаза 63)
    { path: '/mock-imports', label: tk('Mock Test'), icon: 'clipboard', group: 'data' },
    // справочник экзаменов: из него ученик выбирает экзамен для цели (фаза 39)
    { path: '/exam-kinds', label: tk('Экзамены'), icon: 'cap', group: 'data' },
  ],
  director_talent: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    RESOURCES,
    { path: '/subjects', label: tk('Предметы'), icon: 'book', group: 'data' },
    { path: '/tracks', label: tk('Треки'), icon: 'branch', group: 'data' },
  ],
  director_sport: [
    ...DIRECTOR_COMMON,
    TEMPLATES,
    RESOURCES,
    { path: '/sport-types', label: tk('Виды спорта'), icon: 'ball', group: 'data' },
    { path: '/competitions', label: tk('Соревнования'), icon: 'trophy', group: 'data' },
  ],
  // куратор: каждый день — главная, очередь, ученики, документы
  // и посещаемость своих групп; в «Ещё» — то, что открывают раз в неделю
  curator: [
    { path: '/dashboard', label: tk('Главная'), icon: 'home', group: 'work' },
    { path: '/queue', label: tk('Очередь'), icon: 'inbox', group: 'work' },
    { path: '/students', label: tk('Ученики'), icon: 'people', group: 'work' },
    { path: '/documents', label: tk('Документы'), icon: 'docs', group: 'work' },
    // дисциплина по своим группам: куратор её вносит, а не подтверждает
    { path: '/attendance', label: tk('Посещаемость'), icon: 'presence', group: 'work' },
    ...ACADEMICS_CURATOR,
    { path: '/tasks', label: tk('Задачи'), icon: 'checklist', group: 'more' },
    { path: '/journal', label: tk('Журнал изменений'), icon: 'history', group: 'more' },
  ],
  // учитель: сегодня, расписание, журналы и проверка ДЗ; профиль —
  // в меню пользователя, отчётов родителям у него нет (решение владельца)
  teacher: [
    { path: '/dashboard', label: tk('Сегодня'), icon: 'sun', group: 'work' },
    { path: '/schedule', label: tk('Расписание'), icon: 'schedule', group: 'work' },
    { path: '/journals', label: tk('Журналы'), icon: 'book', group: 'work' },
    HOMEWORK_REVIEW,
  ],
  // у администратора дашборд и есть сводный вид — отдельного пункта
  // «Сводный вид» ему не заводим, он вёл бы на тот же экран
  admin: [
    USAGE,
    ...DIRECTOR_COMMON,
    IMPORT,
    ...ACADEMICS,
    // карусель на главной ученика — настройка школы, а не домен директора
    { path: '/home-cues', label: tk('Сюжеты главной'), icon: 'megaphone', group: 'settings' },
    // бейджи учеников — настройка школы (с 28.09.2026 у администратора)
    { path: '/badges', label: tk('Достижения школы'), icon: 'star', group: 'settings' },
    { path: '/users', label: tk('Пользователи'), icon: 'person', group: 'settings' },
    { path: '/archive', label: tk('Архив'), icon: 'box', group: 'settings' },
    { path: '/spend', label: tk('Расходы на ИИ'), icon: 'card', group: 'settings' },
    // пороги и окна школы — настройка администратора, а не константа (30.09.2026)
    { path: '/school-settings', label: tk('Настройки школы'), icon: 'sliders', group: 'settings' },
  ],
}

/**
 * Четыре раздела нижнего бара телефона.
 *
 * Выбраны по частоте работы роли, а не по порядку меню: у ученика —
 * главная, путь, календарь и портфолио (место двух из них займут
 * расписание и оценки, когда придёт учебная часть); у куратора — главная,
 * очередь, ученики и документы; у директоров — кабинет, таблица, очередь
 * решений и один свой домен, а у директора школы вместо таблицы
 * посещаемость и риски; у администратора очереди подтверждений нет
 * (подтверждать ему нечего), поэтому вместо неё «Пользователи».
 *
 * Пятая кнопка бара — «Ещё»: она открывает всё меню целиком теми же
 * группами. Список фильтруется по тому, что роли действительно доступно:
 * «Олимпиадная группа» есть только у того, кто её ведёт.
 */
export const TABS: Record<Role, string[]> = {
  // у ученика в баре — главная, расписание, ДЗ и вузы: ДЗ открывают каждый день,
  // оценки реже — они в «Ещё»; у 8–10 вузов нет, их место добирают оценки
  student: ['/dashboard', '/schedule', '/homework', '/catalog'],
  director_behavior: ['/dashboard', '/attendance', '/risks', '/suggestions'],
  director_admission: ['/dashboard', '/table', '/suggestions', '/directory'],
  director_exam: ['/dashboard', '/table', '/suggestions', '/mocks'],
  director_talent: ['/dashboard', '/table', '/suggestions', '/olympiad-group'],
  director_sport: ['/dashboard', '/table', '/suggestions', '/competitions'],
  curator: ['/dashboard', '/queue', '/students', '/documents'],
  // у учителя четыре раздела: все в баре, профиль — в «Ещё»
  teacher: ['/dashboard', '/schedule', '/journals', '/homework-review'],
  admin: ['/dashboard', '/users', '/table', '/suggestions'],
}

/**
 * Экраны учителя: «Сегодня», расписание, журналы и журнал, урок, профиль,
 * ученик глазами учителя. Список совпадает со шлюзом на сервере
 * (`accounts.permissions.TEACHER_READ_ROUTES`): всё остальное для учителя
 * не существует — сервер отвечает 404, интерфейс уводит на «Сегодня».
 */
export function teacherMayOpen(pathname: string): boolean {
  return (
    ['/dashboard', '/schedule', '/journals', '/profile', '/homework-review'].includes(pathname) ||
    /^\/homework-review\/\d+$/.test(pathname) ||
    /^\/journals\/\d+$/.test(pathname) ||
    /^\/lessons\/\d+$/.test(pathname) ||
    /^\/students\/\d+$/.test(pathname)
  )
}

/** Экраны правки расписания — только у Кымбат и администратора. */
export const SCHEDULE_EDITORS: Role[] = ['director_exam', 'admin']
export const SCHEDULE_EDIT_ONLY = ['/cohorts', '/teachers', '/academic-year']

/** Отчёты родителям делают куратор (свои группы), Кымбат, Салтанат и администратор (все). */
export const REPORT_ROLES: Role[] = ['curator', 'director_exam', 'director_behavior', 'admin']

/**
 * Экраны куратора (фаза 60): кабинет, карточка ученика своей группы, профиль.
 *
 * Список короткий намеренно и совпадает со шлюзом на сервере
 * (`accounts.permissions.CURATOR_READ_ROUTES`): всё остальное — чужие
 * справочники, таблица, импорт, помощник — куратору не открыто ни адресом,
 * ни пунктом меню. Чужого ученика сервер отдаёт как 404.
 */
export function curatorMayOpen(pathname: string): boolean {
  return (
    CURATOR_ONLY.includes(pathname) ||
    CURATOR_SHARED.some((path) => pathname === path || pathname.startsWith(`${path}/`)) ||
    pathname === '/dashboard' ||
    pathname === '/profile' ||
    /^\/students\/\d+$/.test(pathname) ||
    // учебная часть: урок и журнал своей группы — на чтение, чужие сервер отдаёт как 404
    /^\/lessons\/\d+$/.test(pathname) ||
    /^\/journals\/\d+$/.test(pathname)
  )
}

/**
 * Экраны, которые куратор делит с владельцем домена (фаза 63).
 *
 * «Посещаемость» — общий с директором школы (фаза 66): лист один и тот же,
 * разная только граница групп. «Расписание», «Успеваемость» и «Отчёты
 * родителям» — общие с учителем, Кымбат и администратором: адрес один,
 * экран смотрит на роль. Такие экраны не «только кураторские»,
 * поэтому лежат отдельным списком, но открыты куратору так же, как его
 * собственные разделы. «Проверка ДЗ» дополнительно требует своих уроков:
 * отдельный шлюз `homeworkReviewOpen` в App проверяет `teaches`.
 */
export const CURATOR_SHARED = ['/attendance', '/schedule', '/grades', '/reports', '/homework-review']

/**
 * Экраны, которых нет ни у кого, кроме куратора (фаза 61).
 *
 * У директоров своя очередь (`/suggestions`) и своя таблица (`/table`):
 * второй такой же экран им не нужен, а ученику эти адреса закрыты вовсе.
 */
export const CURATOR_ONLY = ['/queue', '/students', '/tasks', '/my-groups', '/documents', '/journal']

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
/** Директор, который ведёт уроки (математика у директора талантов): своя неделя
 *  и отметка своих уроков. Кабинета учителя целиком у него нет. */
const MY_LESSONS: NavItem = { path: '/schedule', label: tk('Мои уроки'), icon: 'schedule', group: 'work' }

export interface NavExtras {
  /** раздел материалов — ученику его открывает олимпиадная группа */
  materials?: boolean
  /** ведёт олимпиадную группу и модерирует материалы */
  curator?: boolean
  /** разделы ученика по параллели его группы (`/auth/me/`, `core/parallels.py`) */
  sections?: string[] | null
  /** ведёт уроки при роли без своего расписания (`/auth/me/` → `teaches`) */
  teaches?: boolean
}

/**
 * Экраны, убранные из кабинета ученика (решение владельца, 07.10.2026): пункта
 * нет, прямой адрес ведёт на главную. Данные и маршруты API остаются — задачи
 * на главной, стипендии и ресурсы у сотрудников. Тот же список на сервере —
 * `core/parallels.py`, `HIDDEN_PATHS`; «Мои вузы» — вкладка каталога.
 */
export const STUDENT_HIDDEN = ['/journey', '/plan', '/scholarships', '/roadmap', '/resources', '/favorites']

/** Все адреса разделов ученика: чтобы понять, что адрес — раздел, закрытый параллели. */
const STUDENT_SECTION_PATHS = [...NAV.student.map((item) => item.path), '/onboarding', '/materials', '/profile', ...STUDENT_HIDDEN]

/**
 * Открыт ли ученику адрес по параллели его группы.
 *
 * Список разделов считает сервер (`core/parallels.py`) — меню, маршруты
 * и шлюз API спрашивают одно и то же место. Адрес, который разделом
 * ученика не является, здесь не решается: для него свои правила.
 */
export function studentMayOpen(sections: string[] | null | undefined, pathname: string): boolean {
  if (!sections) return true
  const section = STUDENT_SECTION_PATHS.find((path) => pathname === path || pathname.startsWith(`${path}/`))
  return section === undefined || sections.includes(section)
}

/** Пункты навигации роли. Флаг «видит всю школу» добавляет сводный вид. */
export function navFor(role: Role, seesWholeSchool = false, extras: NavExtras = {}): NavItem[] {
  let items = NAV[role] ?? []
  if (seesWholeSchool && role !== 'admin' && !items.some((i) => i.path === '/overview')) {
    items = [...items, { path: '/overview', label: tk('Сводный вид'), icon: 'grid', group: 'data' }]
  }
  // пункт «Материалы» появляется только у тех, кому раздел открыт:
  // остальным директорам его не показываем вовсе — там портфолио
  // олимпиадников, и ведёт его директор талантов
  if (extras.materials) {
    items = [...items, { path: '/materials', label: tk('Материалы'), icon: 'folder', group: 'data' }]
  }
  if (extras.curator) {
    // в баре телефона — «Олимпиада»: первое слово «Олимпиадная» само по себе ничего не значит
    items = [
      ...items,
      { path: '/olympiad-group', label: tk('Олимпиадная группа'), icon: 'medal', group: 'data', short: tk('Олимпиада') },
    ]
  }
  if (extras.teaches && role !== 'student' && !items.some((i) => i.path === '/schedule')) {
    items = [...items, MY_LESSONS]
  }
  // ведёт уроки — проверяет и ДЗ своих уроков
  if (homeworkReviewOpen(role, extras.teaches) && !items.some((i) => i.path === '/homework-review')) {
    items = [...items, HOMEWORK_REVIEW]
  }
  // у ученика — только разделы его параллели: блока «Поступление» у 8–10
  // нет вовсе, не под замком
  if (role === 'student' && extras.sections) {
    const open = extras.sections
    items = items.filter((item) => studentMayOpen(open, item.path))
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
  '/achievements',
  '/olympiads',
  '/sport',
  '/homework',
]

/** Экраны сотрудников — ученику закрыты. */
export const STAFF_ONLY = [
  // кабинет куратора (фаза 61): ученику эти адреса закрыты, как и остальные
  '/queue',
  '/students',
  '/tasks',
  '/my-groups',
  '/documents',
  '/journal',
  // посещаемость (фаза 66): её ведёт школа, ученику экран закрыт
  '/attendance',
  // пробники школы (фаза 63): ученик видит свой балл у себя, экран — нет
  '/mock-imports',
  // отчёты родителям: куратор, Кымбат и администратор
  '/reports',
  // учебная часть: журналы, правка расписания, учителя, учебный год — не ученику
  '/journals',
  '/cohorts',
  '/teachers',
  '/academic-year',
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
  '/usage',
  '/school-settings',
]

/** Экраны администратора: люди, архив, расходы и настройка главной ученика. */
export const ADMIN_ONLY = ['/users', '/archive', '/spend', '/home-cues', '/badges', '/school-settings']

/** Кому открыт мастер импорта — тот же список, что `WIZARD_ROLES` на сервере. */
export const IMPORT_ROLES: Role[] = ['admin', 'director_exam']

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
  '/career-questions': 'director_admission',
  '/call-rules': 'director_behavior',
}
