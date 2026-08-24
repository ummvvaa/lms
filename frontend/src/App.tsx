/** Роутинг и провайдеры. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Shell from './layout/Shell'
import { STAFF_ONLY, STUDENT_ONLY } from './layout/nav'
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
import Alumni from './screens/Alumni'
import Digest from './screens/Digest'
import Subjects from './screens/Subjects'
import SportTypes from './screens/SportTypes'
import Materials from './screens/Materials'
import OlympiadGroup from './screens/OlympiadGroup'
import Spend from './screens/Spend'
import Profile from './screens/Profile'
import './screens/screens.css'
import './components/ui.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
})

/** Пускает дальше только с живой сессией и только на экраны своей роли. */
function Protected() {
  const { me, isLoading } = useAuth()
  const location = useLocation()
  if (isLoading) return <div className="login">Загрузка…</div>
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
    (location.pathname === '/overview' && !me.can_see_whole_school)
  if (forbidden) return <Navigate to="/dashboard" replace />

  return <Shell />
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
        <Route path="/alumni" element={<Alumni />} />
        <Route path="/directory" element={<Directory />} />
        <Route path="/archive" element={<Archive />} />
        <Route path="/subjects" element={<Subjects />} />
        <Route path="/sport-types" element={<SportTypes />} />
        <Route path="/materials" element={<Materials />} />
        <Route path="/materials/:id" element={<Materials />} />
        <Route path="/olympiad-group" element={<OlympiadGroup />} />
        <Route path="/spend" element={<Spend />} />
        <Route path="/profile" element={<Profile />} />

        {/* Разделы директоров — секции его же дашборда: маршрут только
            прокручивает к нужному блоку, состав секций у ролей разный */}
        <Route path="/groups" element={<Dashboard />} />
        <Route path="/risks" element={<Dashboard />} />
        <Route path="/overview" element={<Dashboard />} />
        <Route path="/deadlines" element={<Dashboard />} />
        <Route path="/top30" element={<Dashboard />} />
        <Route path="/mocks" element={<Dashboard />} />
        <Route path="/tracks" element={<Dashboard />} />
        <Route path="/competitions" element={<Dashboard />} />

        {/* Экраны ученика */}
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
          <Routing />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
