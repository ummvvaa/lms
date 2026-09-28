/**
 * Адреса всех ролей — контрольный список обхода (фазы 74, 75, 81).
 *
 * Один список на всё: по нему меряет ширину страниц сканер фазы 75 и по нему же
 * ходит обходчик экранов (`screen-walk.spec.ts`). Второго перечня адресов
 * в проекте быть не должно — иначе обход и сканер разойдутся, и «пройдено
 * всё» перестанет что-либо значить.
 *
 * `{id}` — карточка ученика: у куратора своей группы, у директоров и
 * администратора — любого; у учителя — ученик своего состава. `{course}` —
 * журнал учителя, `{lesson}` — урок: подставляет посев учебной части. Список идёт за меню: `/import` — только
 * у администратора и Кымбат, `/career-questions` — у Асем, `/home-cues` —
 * у администратора. Чужой адрес увёл бы на дашборд, и мерили бы не тот экран.
 *
 * Вкладки карточки куратора живут в адресе (`?tab=exams`). У директора
 * и администратора вкладки карточки — состояние экрана, а не адрес: `#rows`
 * и `#history` называют вкладку, которую сканер ширины и каталог экранов
 * открывают нажатием (`CLICK_TABS`). Так же и портфолио ученика: параметр
 * `?tab=documents` экран не читает, вкладка «Документы» открывается нажатием.
 */
export const ROUTES: Record<string, string[]> = {
  student: [
    "/dashboard",
    "/schedule",
    "/grades",
    "/journey",
    "/calendar",
    "/my-data",
    "/my-data?tab=documents",
    "/selection",
    "/catalog",
    "/favorites",
    "/universities",
    "/plan",
    "/scholarships",
    "/career",
    "/essays",
    "/prep",
    "/roadmap",
    "/achievements",
    "/profile",
  ],
  curator: [
    "/dashboard",
    "/queue",
    "/students",
    "/documents",
    "/tasks",
    "/journal",
    "/attendance",
    "/attendance?view=month",
    "/schedule",
    "/grades",
    "/reports",
    "/lessons/{lesson}",
    "/students/{id}",
    "/students/{id}?tab=exams",
    "/students/{id}?tab=grades",
    "/students/{id}?tab=unis",
    "/students/{id}?tab=portfolio",
    "/students/{id}?tab=documents",
    "/students/{id}?tab=notes",
    "/students/{id}?tab=tasks",
  ],
  director_admission: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/deadlines",
    "/directory",
    "/scholarship-directory",
    "/essay-content",
    "/career-questions",
    "/task-templates",
    "/resources",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  teacher: [
    "/dashboard",
    "/schedule",
    "/journals",
    "/journals/{course}",
    "/lessons/{lesson}",
    "/profile",
    "/students/{id}",
  ],
  director_exam: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/schedule",
    "/cohorts",
    "/teachers",
    "/grades",
    "/academic-year",
    "/journals/{course}",
    "/lessons/{lesson}",
    "/mocks",
    "/mock-imports",
    "/reports",
    "/exam-kinds",
    "/top30",
    "/task-templates",
    "/resources",
    "/import",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  director_behavior: [
    "/dashboard",
    "/overview",
    "/suggestions",
    "/table",
    "/contacts",
    "/attendance",
    "/groups",
    "/risks",
    "/call-rules",
    "/resources",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  director_talent: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/olympiad-group",
    "/tracks",
    "/subjects",
    "/materials",
    "/resources",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  director_sport: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/competitions",
    "/sport-types",
    "/resources",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  admin: [
    "/badges",
    "/dashboard",
    "/users",
    "/olympiad-group",
    "/table",
    "/suggestions",
    "/schedule",
    "/cohorts",
    "/teachers",
    "/grades",
    "/reports",
    "/academic-year",
    "/import",
    "/archive",
    "/home-cues",
    "/spend",
    "/students/{id}",
    "/students/{id}#history",
  ],
};

/**
 * Вкладки, которые экран держит в состоянии, а не в адресе: хвост адреса
 * из списка → подпись вкладки. Сканер ширины и каталог экранов открывают
 * такую вкладку нажатием после загрузки.
 */
export const CLICK_TABS: Record<string, string> = {
  "#history": "История изменений",
  "/my-data?tab=documents": "Документы",
};

/** Вкладка, которую адрес из списка открывает нажатием, — или ничего. */
export const clickTab = (route: string): string | undefined =>
  Object.entries(CLICK_TABS).find(([tail]) => route.endsWith(tail))?.[1];
