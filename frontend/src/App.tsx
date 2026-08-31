/** Роутинг и провайдеры. */
import { Fragment, useEffect, useMemo, type ReactNode } from 'react'
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useMaterialsState } from './api/hooks'
import { isNetworkError } from './api/client'
import ConnectionBanner from './components/ConnectionBanner'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { setLanguage } from './i18n'
import { applyDensity, densityFor } from './density'
import { applyTheme } from './theme'
import Shell from './layout/Shell'
import { TooltipProvider } from './components/ui/tooltip'
import { Toaster } from './components/ui/sonner'
import { DOMAIN_ONLY, STAFF_ONLY, STUDENT_ONLY } from './layout/nav'
import LinkLogin from './screens/LinkLogin'
import Login from './screens/Login'
import SetPassword from './screens/SetPassword'
import ChangePassword from './screens/ChangePassword'
import Users from './screens/Users'
import Dashboard from './screens/dashboards/Dashboard'
import TableScreen from './screens/TableScreen'
import StudentCardScreen from './screens/StudentCard'
import ImportScreen from './screens/ImportScreen'
import MyUniversities from './screens/MyUniversities'
import Catalog from './screens/Catalog'
import Directory from './screens/Directory'
import Archive from './screens/Archive'
import Onboarding from './screens/Onboarding'
import Prep from './screens/Prep'
import Roadmap from './screens/Roadmap'
import Essays from './screens/Essays'
import Assistant from './screens/Assistant'
import Suggestions from './screens/Suggestions'
import Digest from './screens/Digest'
import Subjects from './screens/Subjects'
import SportTypes from './screens/SportTypes'
import Materials from './screens/Materials'
import OlympiadGroup from './screens/OlympiadGroup'
import Spend from './screens/Spend'
import Contacts from './screens/Contacts'
import TaskTemplates from './screens/TaskTemplates'
import MyData from './screens/MyData'
import Journey from './screens/Journey'
import Calendar from './screens/Calendar'
import ExamKinds from './screens/ExamKinds'
import Selection from './screens/Selection'
import Favorites from './screens/Favorites'
import Plan from './screens/Plan'
import Profile from './screens/Profile'
import OverviewDashboard from './screens/dashboards/OverviewDashboard'
import Groups from './screens/sections/Groups'
import Risks from './screens/sections/Risks'
import Deadlines from './screens/sections/Deadlines'
import Top30 from './screens/sections/Top30'
import Mocks from './screens/sections/Mocks'
import Tracks from './screens/sections/Tracks'
import Competitions from './screens/sections/Competitions'
import './screens/screens.css'
import './components/ui.css'
import { t } from './i18n'

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
  const { me, isLoading } = useAuth()
  // `isLoading` здесь — «ответа о сессии ещё не было»: и пока он идёт,
  // и пока сервер молчит. Уводить на вход можно только по ответу 401/403,
  // а не по его отсутствию (фаза 36, D3)
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
    // управление людьми — только у роли `admin`, она техническая
    ((location.pathname === '/users' || location.pathname === '/archive' || location.pathname === '/spend') &&
      me.role !== 'admin') ||
    // справочник ведёт его домен: чужому директору там нечего делать
    (location.pathname === '/subjects' && me.role !== 'director_talent') ||
    (location.pathname === '/sport-types' && me.role !== 'director_sport') ||
    // олимпиадную группу отбирает директор талантов
    (location.pathname === '/olympiad-group' && me.role !== 'director_talent') ||
    // раздел материалов олимпиадников: ведёт его директор талантов,
    // читают ученики из группы. Остальным его нет — ни пункта, ни адреса
    (location.pathname.startsWith('/materials') && materials.data?.has_access === false) ||
    // раздел домена — только у его директора: пункта меню у остальных нет,
    // и прямой адрес возвращает туда же, куда ведёт отсутствующий пункт
    (DOMAIN_ONLY[location.pathname] !== undefined && me.role !== DOMAIN_ONLY[location.pathname]) ||
    (location.pathname === '/overview' && !me.can_see_whole_school)
  if (forbidden) return <Navigate to="/dashboard" replace />

  return <Shell />
}

/**
 * Личные настройки из профиля: тема, язык и плотность.
 *
 * Язык выставляется до отрисовки детей (useMemo, не useEffect), а ключ
 * перемонтирует поддерево при смене — интерфейс меняется без перезагрузки.
 * Плотность приходит не из профиля, а из роли: это не вкус, а разные
 * задачи — таблица на 250 строк и кабинет с тремя задачами.
 */
function PersonalSettings({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const lang = me?.language ?? 'ru'
  const theme = me?.theme ?? 'system'
  useMemo(() => setLanguage(lang), [lang])
  useEffect(() => applyTheme(theme), [theme])
  useEffect(() => applyDensity(densityFor(me?.role)), [me?.role])
  return (
    <Fragment key={lang}>
      {/* полоса «нет связи» — над любым экраном, включая вход */}
      <ConnectionBanner />
      <TooltipProvider>{children}</TooltipProvider>
      {/* Всплывающие уведомления. Тему передаём из профиля явно: сам `Toaster`
          спрашивает её у `next-themes`, которого в проекте нет, и без этого
          молча уходил бы на системную — а выбор руками должен её перекрывать */}
      <Toaster theme={theme} position="bottom-right" />
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

      <Route element={<Protected />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/table" element={<TableScreen />} />
        <Route path="/students/:id" element={<StudentCardScreen />} />
        <Route path="/import" element={<ImportScreen />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/suggestions" element={<Suggestions />} />
        <Route path="/suggestions/:id" element={<Suggestions />} />
        <Route path="/digest" element={<Digest />} />
        <Route path="/users" element={<Users />} />
        <Route path="/directory" element={<Directory />} />
        <Route path="/archive" element={<Archive />} />
        <Route path="/subjects" element={<Subjects />} />
        <Route path="/sport-types" element={<SportTypes />} />
        <Route path="/exam-kinds" element={<ExamKinds />} />
        <Route path="/materials" element={<Materials />} />
        <Route path="/materials/:id" element={<Materials />} />
        <Route path="/olympiad-group" element={<OlympiadGroup />} />
        <Route path="/spend" element={<Spend />} />
        <Route path="/profile" element={<Profile />} />

        {/* Разделы директоров — отдельные экраны со своими адресами */}
        <Route path="/groups" element={<Groups />} />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/task-templates" element={<TaskTemplates />} />
        <Route path="/risks" element={<Risks />} />
        <Route path="/overview" element={<OverviewDashboard />} />
        <Route path="/deadlines" element={<Deadlines />} />
        <Route path="/top30" element={<Top30 />} />
        <Route path="/mocks" element={<Mocks />} />
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
        <Route path="/roadmap" element={<Roadmap />} />
        <Route path="/universities" element={<MyUniversities />} />
        <Route path="/catalog" element={<Catalog />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/prep" element={<Prep />} />
        <Route path="/essays" element={<Essays />} />
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
