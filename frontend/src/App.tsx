/** Роутинг и провайдеры. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Shell from './layout/Shell'
import { STAFF_ONLY, STUDENT_ONLY } from './layout/nav'
import LinkLogin from './screens/LinkLogin'
import Login from './screens/Login'
import Dashboard from './screens/dashboards/Dashboard'
import TableScreen from './screens/TableScreen'
import StudentCardScreen from './screens/StudentCard'
import ImportScreen from './screens/ImportScreen'
import MyUniversities from './screens/MyUniversities'
import Roadmap from './screens/Roadmap'
import Essays from './screens/Essays'
import Assistant from './screens/Assistant'
import Suggestions from './screens/Suggestions'
import Alumni from './screens/Alumni'
import Digest from './screens/Digest'
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

  // экран чужой роли открывать нечем: у сотрудника нет карточки ученика,
  // у ученика нет домена. Раньше такой адрес рисовал полупустой экран
  // и сыпал 404 в консоль
  const isStudent = me.role === 'student'
  const forbidden = isStudent
    ? STAFF_ONLY.includes(location.pathname)
    : STUDENT_ONLY.includes(location.pathname)
  if (forbidden) return <Navigate to="/dashboard" replace />

  return <Shell />
}

function Routing() {
  const { me, isLoading } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={me && !isLoading ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/login/link" element={<LinkLogin />} />

      <Route element={<Protected />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/table" element={<TableScreen />} />
        <Route path="/students/:id" element={<StudentCardScreen />} />
        <Route path="/import" element={<ImportScreen />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/suggestions" element={<Suggestions />} />
        <Route path="/suggestions/:id" element={<Suggestions />} />
        <Route path="/digest" element={<Digest />} />
        <Route path="/alumni" element={<Alumni />} />

        {/* Разделы директоров — секции его же дашборда: маршрут только
            прокручивает к нужному блоку, состав секций у ролей разный */}
        <Route path="/groups" element={<Dashboard />} />
        <Route path="/risks" element={<Dashboard />} />
        <Route path="/overview" element={<Dashboard />} />
        <Route path="/deadlines" element={<Dashboard />} />
        <Route path="/top30" element={<Dashboard />} />
        <Route path="/tracks" element={<Dashboard />} />
        <Route path="/competitions" element={<Dashboard />} />

        {/* Экраны ученика */}
        <Route path="/roadmap" element={<Roadmap />} />
        <Route path="/universities" element={<MyUniversities />} />
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
