/** Роутинг и провайдеры. */
import { Fragment, lazy, useEffect, useMemo, useReducer, type ReactNode } from 'react'
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useMaterialsState } from './api/hooks'
import { isNetworkError } from './api/client'
import ConnectionBanner from './components/ConnectionBanner'
import OfflineScreen from './components/OfflineScreen'
import { useConnection } from './api/useConnection'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { language, languageReady, loadLanguage, rememberLanguage, setLanguage } from './i18n'
import { offeredLanguage } from './components/ProfileMenu'
import { applyTheme } from './theme'
import Shell from './layout/Shell'
import { TooltipProvider } from './components/ui/tooltip'
import { Toaster } from './components/ui/sonner'
import {
  ADMIN_ONLY,
  CURATOR_ONLY,
  curatorMayOpen,
  DOMAIN_ONLY,
  homeworkReviewOpen,
  IMPORT_ROLES,
  SCHEDULE_EDIT_ONLY,
  REPORT_ROLES,
  SCHEDULE_EDITORS,
  STAFF_ONLY,
  STUDENT_ONLY,
  studentMayOpen,
  teacherMayOpen,
} from './layout/nav'
import LinkLogin from './screens/LinkLogin'
import Login from './screens/Login'
import SetPassword from './screens/SetPassword'
import ChangePassword from './screens/ChangePassword'
import ConfirmEmail from './screens/ConfirmEmail'
// стили экранов — сразу и в прежнем порядке, сами экраны — по маршруту
import './screenStyles'
import './screens/screens.css'
// стили общих компонентов, описанные раньше в CSS экранов: место в каскаде —
// сразу за `screens.css`, откуда они переехали
import './components/password-rules.css'
import './components/account-forms.css'
import './components/rowmenu.css'
import './components/propose.css'
import './components/student-queue.css'
import './components/exam-goals.css'
import './components/handout.css'
import './components/import-wizard.css'
import './components/material-card.css'
import './components/ui.css'
import { t } from './i18n'

// Экраны грузятся по маршруту: одна сборка на все роли весила 2,4 МБ и
// росла с каждым разделом, а ученик скачивал журналы, импорт и обзор школы.
// Вход и смена пароля — сразу: они нужны до того, как известна роль
const Users = lazy(() => import('./screens/Users'))
const CuratorQueue = lazy(() => import('./screens/curator/Queue'))
const CuratorStudents = lazy(() => import('./screens/curator/Students'))
const CuratorTasks = lazy(() => import('./screens/curator/Tasks'))
const CuratorGroups = lazy(() => import('./screens/curator/Groups'))
const CuratorDocuments = lazy(() => import('./screens/curator/Documents'))
const CuratorJournal = lazy(() => import('./screens/curator/Journal'))
const Attendance = lazy(() => import('./screens/Attendance'))
const MockImports = lazy(() => import('./screens/mocks/MockImports'))
const MockResults = lazy(() => import('./screens/mocks/MockImports').then((module) => ({ default: module.MockResults })))
const Dashboard = lazy(() => import('./screens/dashboards/Dashboard'))
const TableScreen = lazy(() => import('./screens/TableScreen'))
const ImportScreen = lazy(() => import('./screens/ImportScreen'))
const MyUniversities = lazy(() => import('./screens/MyUniversities'))
const Catalog = lazy(() => import('./screens/Catalog'))
const Directory = lazy(() => import('./screens/Directory'))
const Archive = lazy(() => import('./screens/Archive'))
const Onboarding = lazy(() => import('./screens/Onboarding'))
const Prep = lazy(() => import('./screens/Prep'))
const Roadmap = lazy(() => import('./screens/Roadmap'))
const Essays = lazy(() => import('./screens/Essays'))
const Assistant = lazy(() => import('./screens/Assistant'))
const Suggestions = lazy(() => import('./screens/Suggestions'))
const Digest = lazy(() => import('./screens/Digest'))
const Subjects = lazy(() => import('./screens/Subjects'))
const SportTypes = lazy(() => import('./screens/SportTypes'))
const Materials = lazy(() => import('./screens/Materials'))
const OlympiadGroup = lazy(() => import('./screens/OlympiadGroup'))
const Spend = lazy(() => import('./screens/Spend'))
const SchoolSettings = lazy(() => import('./screens/SchoolSettings'))
const Contacts = lazy(() => import('./screens/Contacts'))
const TaskTemplates = lazy(() => import('./screens/TaskTemplates'))
const MyData = lazy(() => import('./screens/MyData'))
const Olympiads = lazy(() => import('./screens/Olympiads'))
const Sport = lazy(() => import('./screens/Sport'))
const Journey = lazy(() => import('./screens/Journey'))
const Calendar = lazy(() => import('./screens/Calendar'))
const ExamKinds = lazy(() => import('./screens/ExamKinds'))
const Selection = lazy(() => import('./screens/Selection'))
const Favorites = lazy(() => import('./screens/Favorites'))
const Plan = lazy(() => import('./screens/Plan'))
const EssayContent = lazy(() => import('./screens/EssayContent'))
const Scholarships = lazy(() => import('./screens/Scholarships'))
const ScholarshipDirectory = lazy(() => import('./screens/ScholarshipDirectory'))
const Resources = lazy(() => import('./screens/Resources'))
const Career = lazy(() => import('./screens/Career'))
const CareerQuestions = lazy(() => import('./screens/CareerQuestions'))
const HomeCues = lazy(() => import('./screens/HomeCues'))
const CallRules = lazy(() => import('./screens/CallRules'))
const Achievements = lazy(() => import('./screens/Achievements'))
const Badges = lazy(() => import('./screens/Badges'))
const Profile = lazy(() => import('./screens/Profile'))
const ScheduleScreen = lazy(() => import('./screens/academics/ScheduleScreen'))
const Journals = lazy(() => import('./screens/academics/Journals'))
const Journal = lazy(() => import('./screens/academics/Journal'))
const LessonScreen = lazy(() => import('./screens/academics/Lesson'))
const Cohorts = lazy(() => import('./screens/academics/Cohorts'))
const Teachers = lazy(() => import('./screens/academics/Teachers'))
const GradesScreen = lazy(() => import('./screens/academics/GradesScreen'))
const AcademicYear = lazy(() => import('./screens/academics/AcademicYear'))
const Reports = lazy(() => import('./screens/academics/Reports'))
const StudentRoute = lazy(() => import('./screens/academics/StudentRoute'))
const HomeworkReview = lazy(() => import('./screens/academics/HomeworkReview'))
const HomeworkCheck = lazy(() => import('./screens/academics/HomeworkCheck'))
const MyHomeworkScreen = lazy(() => import('./screens/homework/MyHomework'))
const MyHomeworkDetailScreen = lazy(() => import('./screens/homework/MyHomeworkDetail'))
const OverviewDashboard = lazy(() => import('./screens/dashboards/OverviewDashboard'))
const Groups = lazy(() => import('./screens/sections/Groups'))
const Risks = lazy(() => import('./screens/sections/Risks'))
const Deadlines = lazy(() => import('./screens/sections/Deadlines'))
const Top30 = lazy(() => import('./screens/sections/Top30'))
const Mocks = lazy(() => import('./screens/sections/Mocks'))
const Tracks = lazy(() => import('./screens/sections/Tracks'))
const Competitions = lazy(() => import('./screens/sections/Competitions'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // сетевую ошибку повторяем с нарастающей задержкой; пока сервер не
      // отвечает, `connection.ts` держит запросы на паузе, и повторы
      // не молотят впустую. Ответ сервера (401, 404, 500 с телом) — не повод
      // повторять: это ответ, а не его отсутствие (фаза 36, D3)
      retry: (count, error) => (isNetworkError(error) ? count < 3 : count < 1),
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 15_000),
    },
  },
  // Уведомление о сохранении — одно на всё приложение. Мутация, помеченная
  // `meta.saved`, после успеха показывает «Сохранено»; экранам не нужно
  // помнить об этом каждому. Таблица быстрого ввода и предложения пишут
  // своё, более точное сообщение сами и пометки не несут
  mutationCache: new MutationCache({
    onSuccess: (_data, _variables, _context, mutation) => {
      if (mutation.meta?.saved) toast.success(t('Сохранено'))
    },
  }),
})

/** Пускает дальше только с живой сессией и только на экраны своей роли. */
function Protected() {
  const { me, isLoading, failed, retry } = useAuth()
  const { offline } = useConnection()
  // `isLoading` здесь — «ответа о сессии ещё не было»: и пока он идёт,
  // и пока сервер молчит. Уводить на вход можно только по ответу 401/403,
  // а не по его отсутствию (фаза 36, D3). Молчание сервера — свой экран
  // с «Повторить», а не пустое поле и не экран входа (фаза 76)
  if (failed || (isLoading && offline)) return <OfflineScreen onRetry={retry} />
  if (isLoading) return <div className="login">{t('Загрузка…')}</div>
  if (!me) return <Navigate to="/login" replace />

  // выданный школой пароль знает ещё кто-то: пока он не сменён, работать
  // в системе нельзя. Сервер тем же условием отбивает любой другой запрос.
  // Экран смены пароля рисуется до любых фоновых запросов оболочки:
  // на нём ничего не должно лететь параллельно (фаза 36, D1)
  if (me.must_change_password) return <ChangePassword />

  return <ProtectedShell me={me} />
}

function ProtectedShell({ me }: { me: NonNullable<ReturnType<typeof useAuth>['me']> }) {
  const location = useLocation()
  // тем же ответом сервера, что и меню: раздел материалов есть не у всех
  const materials = useMaterialsState()

  // экран чужой роли открывать нечем: у сотрудника нет карточки ученика,
  // у ученика нет домена. Раньше такой адрес рисовал полупустой экран
  // и сыпал 404 в консоль
  const isStudent = me.role === 'student'
  const forbidden =
    (isStudent ? STAFF_ONLY : STUDENT_ONLY).includes(location.pathname) ||
    // ученику — разделы его параллели: поступление у 8–10 закрыто и по адресу
    (isStudent && !studentMayOpen(me.sections, location.pathname)) ||
    // управление людьми — только у роли `admin`, она техническая
    (ADMIN_ONLY.includes(location.pathname) && me.role !== 'admin') ||
    // мастер импорта — у администратора и Кымбат; остальные вносят руками
    (location.pathname === '/import' && !IMPORT_ROLES.includes(me.role)) ||
    // справочник ведёт его домен: чужому директору там нечего делать
    (location.pathname === '/subjects' && me.role !== 'director_talent') ||
    (location.pathname === '/sport-types' && me.role !== 'director_sport') ||
    // олимпиадную группу отбирает директор талантов; администратор правит все домены
    (location.pathname === '/olympiad-group' && !['director_talent', 'admin'].includes(me.role)) ||
    // раздел материалов олимпиадников: ведёт его директор талантов,
    // читают ученики из группы. Остальным его нет — ни пункта, ни адреса
    (location.pathname.startsWith('/materials') && materials.data?.has_access === false) ||
    // раздел домена — только у его директора: пункта меню у остальных нет,
    // и прямой адрес возвращает туда же, куда ведёт отсутствующий пункт
    (DOMAIN_ONLY[location.pathname] !== undefined && me.role !== DOMAIN_ONLY[location.pathname]) ||
    (location.pathname === '/overview' && !me.can_see_whole_school) ||
    // куратору открыт короткий список экранов — тот же, что и на сервере (фаза 60)
    (me.role === 'curator' && !curatorMayOpen(location.pathname)) ||
    // учителю — семь адресов; всё остальное для него не существует
    (me.role === 'teacher' && !teacherMayOpen(location.pathname)) ||
    // правка расписания, составы, учителя и учебный год — у Кымбат и администратора
    (SCHEDULE_EDIT_ONLY.includes(location.pathname) && !SCHEDULE_EDITORS.includes(me.role)) ||
    // журналы списком — только у учителя; журнал по адресу открыт и Кымбат с куратором
    (location.pathname === '/journals' && me.role !== 'teacher') ||
    // проверка ДЗ — учитель, Кымбат, администратор и тот, кто ведёт уроки
    ((location.pathname === '/homework-review' || location.pathname.startsWith('/homework-review/')) && !homeworkReviewOpen(me.role, me.teaches)) ||
    // отчёты родителям — куратор, Кымбат и администратор
    (location.pathname === '/reports' && !REPORT_ROLES.includes(me.role)) ||
    // и наоборот: экраны кабинета куратора не открываются никому другому (фаза 61)
    (CURATOR_ONLY.includes(location.pathname) && me.role !== 'curator')
  if (forbidden) return <Navigate to="/dashboard" replace />

  return <Shell />
}

/**
 * Личные настройки из профиля: тема, язык и плотность.
 *
 * Язык выставляется до отрисовки детей (useMemo, не useEffect), а ключ
 * перемонтирует поддерево при смене — интерфейс меняется без перезагрузки.
 * Словарь языка подгружается отдельным куском сборки: до его прихода
 * остаётся прежний язык.
 * Плотность приходит не из профиля, а из роли: это не вкус, а разные
 * задачи — таблица на 250 строк и кабинет с тремя задачами.
 */
function PersonalSettings({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  // сохранённый в профиле язык действует, только если он предлагается; до входа — язык устройства
  const wanted = offeredLanguage(me)
  // словарь — отдельный кусок сборки: пока он едет, интерфейс остаётся на
  // прежнем языке и переключается целиком, когда словарь в памяти
  const [, arrived] = useReducer((count: number) => count + 1, 0)
  const lang = languageReady(wanted) ? wanted : language()
  useEffect(() => {
    if (languageReady(wanted)) return
    let live = true
    loadLanguage(wanted).then(
      () => live && arrived(),
      // нет связи: язык остаётся прежним, полоса «нет связи» уже на экране
      () => undefined,
    )
    return () => {
      live = false
    }
  }, [wanted])
  const theme = me?.theme ?? 'system'
  useMemo(() => setLanguage(lang), [lang])
  useEffect(() => {
    // запоминается выбранный язык: с него устройство начнёт в следующий раз
    if (me) rememberLanguage(wanted)
  }, [me, wanted])
  useEffect(() => applyTheme(theme), [theme])
  return (
    <Fragment key={lang}>
      {/* полоса «нет связи» — над любым экраном, включая вход */}
      <ConnectionBanner />
      <TooltipProvider>{children}</TooltipProvider>
      {/* Всплывающие уведомления: внизу по центру, пять секунд, с крестиком
          (фаза 69). Правый нижний угол перекрывал последние строки таблицы
          на экране «Пользователи» — там двести строк, и нижние важны так же,
          как верхние. Несколько тостов подряд складываются стопкой сами.
          Тему передаём из профиля явно: сам `Toaster`
          спрашивает её у `next-themes`, которого в проекте нет, и без этого
          молча уходил бы на системную — а выбор руками должен её перекрывать */}
      <Toaster theme={theme} position="bottom-center" duration={5000} closeButton />
    </Fragment>
  )
}

function Routing() {
  const { me, isLoading } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={me && !isLoading ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/login/link" element={<LinkLogin />} />
      <Route path="/set-password" element={<SetPassword />} />
      <Route path="/confirm-email" element={<ConfirmEmail />} />

      <Route element={<Protected />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/table" element={<TableScreen />} />
        <Route path="/students/:id" element={<StudentRoute />} />
        <Route path="/import" element={<ImportScreen />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/suggestions" element={<Suggestions />} />
        <Route path="/suggestions/:id" element={<Suggestions />} />
        <Route path="/digest" element={<Digest />} />
        <Route path="/users" element={<Users />} />

        {/* Кабинет куратора (фаза 61): очередь, ученики, задачи, свои группы */}
        <Route path="/queue" element={<CuratorQueue />} />
        <Route path="/students" element={<CuratorStudents />} />
        <Route path="/tasks" element={<CuratorTasks />} />
        <Route path="/my-groups" element={<CuratorGroups />} />
        <Route path="/documents" element={<CuratorDocuments />} />
        <Route path="/journal" element={<CuratorJournal />} />
        {/* посещаемость (фаза 66): один экран на куратора и директора школы */}
        <Route path="/attendance" element={<Attendance />} />
        <Route path="/directory" element={<Directory />} />
        <Route path="/archive" element={<Archive />} />
        <Route path="/subjects" element={<Subjects />} />
        <Route path="/sport-types" element={<SportTypes />} />
        <Route path="/exam-kinds" element={<ExamKinds />} />
        <Route path="/materials" element={<Materials />} />
        <Route path="/materials/:id" element={<Materials />} />
        <Route path="/olympiad-group" element={<OlympiadGroup />} />
        <Route path="/spend" element={<Spend />} />
        <Route path="/school-settings" element={<SchoolSettings />} />
        <Route path="/profile" element={<Profile />} />

        {/* Учебная часть: расписание у учителя, куратора, Кымбат и администратора;
            журналы и урок; составы, учителя, успеваемость, учебный год */}
        <Route path="/schedule" element={<ScheduleScreen />} />
        <Route path="/journals" element={<Journals />} />
        <Route path="/journals/:id" element={<Journal />} />
        <Route path="/lessons/:id" element={<LessonScreen />} />
        {/* сдача ДЗ: список заданий на проверку и проверка работ одного задания */}
        <Route path="/homework-review" element={<HomeworkReview />} />
        <Route path="/homework-review/:id" element={<HomeworkCheck />} />
        {/* сдача ДЗ глазами ученика: задания по вкладкам и одно задание со своей работой */}
        <Route path="/homework" element={<MyHomeworkScreen />} />
        <Route path="/homework/:id" element={<MyHomeworkDetailScreen />} />
        <Route path="/cohorts" element={<Cohorts />} />
        <Route path="/teachers" element={<Teachers />} />
        <Route path="/grades" element={<GradesScreen />} />
        <Route path="/academic-year" element={<AcademicYear />} />
        <Route path="/reports" element={<Reports />} />

        {/* Разделы директоров — отдельные экраны со своими адресами */}
        <Route path="/groups" element={<Groups />} />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/task-templates" element={<TaskTemplates />} />
        <Route path="/risks" element={<Risks />} />
        <Route path="/overview" element={<OverviewDashboard />} />
        <Route path="/deadlines" element={<Deadlines />} />
        <Route path="/top30" element={<Top30 />} />
        <Route path="/mocks" element={<Mocks />} />
        {/* пробники файлом (фаза 63): список, результаты. Адрес свой,
            а не «/mocks»: там пробные экзамены платформы у Кымбат */}
        <Route path="/mock-imports" element={<MockImports />} />
        <Route path="/mock-imports/:id" element={<MockResults />} />
        <Route path="/tracks" element={<Tracks />} />
        <Route path="/competitions" element={<Competitions />} />

        {/* Экраны ученика */}
        <Route path="/journey" element={<Journey />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/selection" element={<Selection />} />
        <Route path="/selection/:id" element={<Selection />} />
        <Route path="/favorites" element={<Favorites />} />
        <Route path="/plan" element={<Plan />} />
        <Route path="/plan/:id" element={<Plan />} />
        <Route path="/my-data" element={<MyData />} />
        <Route path="/olympiads" element={<Olympiads />} />
        <Route path="/sport" element={<Sport />} />
        <Route path="/roadmap" element={<Roadmap />} />
        <Route path="/universities" element={<MyUniversities />} />
        <Route path="/catalog" element={<Catalog />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/prep" element={<Prep />} />
        <Route path="/essays" element={<Essays />} />
        <Route path="/essay-content" element={<EssayContent />} />
        <Route path="/scholarships" element={<Scholarships />} />
        <Route path="/scholarship-directory" element={<ScholarshipDirectory />} />
        {/* ресурсы читают все роли: раздел не закрыт ни доменом, ни группой */}
        <Route path="/resources" element={<Resources />} />
        <Route path="/resources/:id" element={<Resources />} />
        <Route path="/career" element={<Career />} />
        <Route path="/career-questions" element={<CareerQuestions />} />
        {/* справочники фазы 49: сюжеты главной ученика и правила обзвона */}
        <Route path="/home-cues" element={<HomeCues />} />
        <Route path="/call-rules" element={<CallRules />} />
        <Route path="/achievements" element={<Achievements />} />
        <Route path="/badges" element={<Badges />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <PersonalSettings>
            <Routing />
          </PersonalSettings>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
