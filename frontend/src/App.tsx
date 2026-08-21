/** Роутинг и провайдеры. Экраны-заглушки наполняются в Фазах 3–6. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Shell from './layout/Shell'
import LinkLogin from './screens/LinkLogin'
import Login from './screens/Login'
import Placeholder from './screens/Placeholder'
import Dashboard from './screens/dashboards/Dashboard'
import TableScreen from './screens/TableScreen'
import StudentCardScreen from './screens/StudentCard'
import ImportScreen from './screens/ImportScreen'
import './screens/screens.css'
import './components/ui.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
})

/** Пускает дальше только с живой сессией. */
function Protected() {
  const { me, isLoading } = useAuth()
  if (isLoading) return <div className="login">Загрузка…</div>
  if (!me) return <Navigate to="/login" replace />
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

        {/* Разделы директоров ведут на их дашборд — состав секций у ролей разный */}
        <Route path="/groups" element={<Dashboard />} />
        <Route path="/risks" element={<Dashboard />} />
        <Route path="/overview" element={<Dashboard />} />
        <Route path="/deadlines" element={<Dashboard />} />
        <Route path="/top30" element={<Dashboard />} />
        <Route path="/tracks" element={<Dashboard />} />
        <Route path="/competitions" element={<Dashboard />} />

        {/* Наполняются в Фазах 4 и 6 */}
        <Route
          path="/roadmap"
          element={<Placeholder emoji="▤" title="Роадмап" note="Задачи по месяцам и доска — Фаза 4." />}
        />
        <Route
          path="/universities"
          element={<Placeholder emoji="⌂" title="Мои вузы" note="Соответствие требованиям — Фаза 4." />}
        />
        <Route
          path="/essays"
          element={<Placeholder emoji="✎" title="Эссе" note="Работа над эссе — Фаза 4." />}
        />
        <Route
          path="/alumni"
          element={<Placeholder emoji="◍" title="Выпускники" note="Каталог и менторство — Фаза 6." />}
        />
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
