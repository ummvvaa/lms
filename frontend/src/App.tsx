/** Роутинг и провайдеры. Экраны-заглушки наполняются в Фазах 3–6. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Shell from './layout/Shell'
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
import Alumni from './screens/Alumni'
import Digest from './screens/Digest'
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
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/digest" element={<Digest />} />
        <Route path="/alumni" element={<Alumni />} />

        {/* Разделы директоров ведут на их дашборд — состав секций у ролей разный */}
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
