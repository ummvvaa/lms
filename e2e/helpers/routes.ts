/**
 * Адреса всех ролей — контрольный список обхода (фазы 74, 75, 81).
 *
 * Один список на всё: по нему меряет ширину страниц сканер фазы 75 и по нему же
 * ходит обходчик экранов (`screen-walk.spec.ts`). Второго перечня адресов
 * в проекте быть не должно — иначе обход и сканер разойдутся, и «пройдено
 * всё» перестанет что-либо значить.
 *
 * `{id}` — карточка ученика: у куратора своей группы, у директоров — любого.
 * Список идёт за меню: `/import` — только у администратора и Кымбат,
 * `/career-questions` — у Асем, `/home-cues` — у администратора. Чужой адрес
 * увёл бы на дашборд, и мерили бы не тот экран.
 */
export const ROUTES: Record<string, string[]> = {
  student: [
    "/dashboard",
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
    "/quiz",
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
    "/mock-imports",
    "/students/{id}",
    "/students/{id}?tab=exams",
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
  director_exam: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/mocks",
    "/mock-imports",
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
    "/badges",
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
    "/dashboard",
    "/users",
    "/table",
    "/suggestions",
    "/import",
    "/archive",
    "/mail-templates",
    "/home-cues",
    "/spend",
  ],
};

/** Сколько всего адресов в контрольном списке. */
export const ROUTE_COUNT = Object.values(ROUTES).reduce(
  (sum, list) => sum + list.length,
  0,
);

/** Роли обхода в том порядке, в каком за систему садятся люди. */
export const WALK_ROLES = Object.keys(ROUTES);
