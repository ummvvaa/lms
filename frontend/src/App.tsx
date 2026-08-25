/** Роутинг и провайдеры. */
import { Fragment, useEffect, useMemo, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useMaterialsState } from './api/hooks'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { setLanguage } from './i18n'
import { applyTheme } from './theme'
import Shell from './layout/Shell'
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
import MyData from './screens/MyData'
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
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
})

/** Пускает дальше только с живой сессией и только на экраны своей роли. */
function Protected() {
  const { me, isLoading } = useAuth()
  const location = useLocation()
  // тем же ответом сервера, что и меню: раздел материалов есть не у всех
  const materials = useMaterialsState()
  if (isLoading) return <div className="login">{t('Загрузка…')}</div>
  if (!me) return <Navigate to="/login" replace />

  // выданный школой пароль знает ещё кто-то: пока он не сменён, работать
  // в системе нельзя. Сервер тем же условием отбивает любой другой запрос
  if (me.must_change_password) return <ChangePassword />

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
 * Личные настройки из профиля: тема и язык.
 *
 * Язык выставляется до отрисовки детей (useMemo, не useEffect), а ключ
 * перемонтирует поддерево при смене — интерфейс меняется без перезагрузки.
 */
function PersonalSettings({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const lang = me?.language ?? 'ru'
  const theme = me?.theme ?? 'system'
  useMemo(() => setLanguage(lang), [lang])
  useEffect(() => applyTheme(theme), [theme])
  return <Fragment key={lang}>{children}</Fragment>
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
        <Route path="/materials" element={<Materials />} />
        <Route path="/materials/:id" element={<Materials />} />
        <Route path="/olympiad-group" element={<OlympiadGroup />} />
        <Route path="/spend" element={<Spend />} />
        <Route path="/profile" element={<Profile />} />

        {/* Разделы директоров — отдельные экраны со своими адресами */}
        <Route path="/groups" element={<Groups />} />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/risks" element={<Risks />} />
        <Route path="/overview" element={<OverviewDashboard />} />
        <Route path="/deadlines" element={<Deadlines />} />
        <Route path="/top30" element={<Top30 />} />
        <Route path="/mocks" element={<Mocks />} />
        <Route path="/tracks" element={<Tracks />} />
        <Route path="/competitions" element={<Competitions />} />

        {/* Экраны ученика */}
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
