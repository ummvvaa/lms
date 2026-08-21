/** Роутинг и провайдеры. Экраны-заглушки наполняются в Фазах 3–6. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Shell from './layout/Shell'
import LinkLogin from './screens/LinkLogin'
import Login from './screens/Login'
import Placeholder from './screens/Placeholder'
import './screens/screens.css'

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
        <Route
          path="/dashboard"
          element={<Placeholder emoji="◎" title="Дашборд" note="Дашборды по ролям появятся в Фазе 3." />}
        />
        <Route
          path="/table"
          element={<Placeholder emoji="⌗" title="Таблица" note="Плотный табличный ввод — Фаза 3." />}
        />
        <Route
          path="/groups"
          element={
            <Placeholder emoji="▤" title="Группы" note="Заполненность и светофор по группам — Фаза 3." />
          }
        />
        <Route
          path="/risks"
          element={<Placeholder emoji="!" title="Риски" note="Кому звонить сегодня — Фаза 3." />}
        />
        <Route
          path="/overview"
          element={<Placeholder emoji="◍" title="Сводный вид" note="Вся школа в пяти цифрах — Фаза 3." />}
        />
        <Route
          path="/deadlines"
          element={<Placeholder emoji="⏱" title="Дедлайны" note="Календарь дедлайнов вузов — Фаза 3." />}
        />
        <Route
          path="/top30"
          element={<Placeholder emoji="★" title="TOP-30" note="Кандидаты на прорыв — Фаза 3." />}
        />
        <Route
          path="/tracks"
          element={<Placeholder emoji="▤" title="Треки" note="Шесть направлений усиления — Фаза 3." />}
        />
        <Route
          path="/competitions"
          element={<Placeholder emoji="⏱" title="Соревнования" note="Календарь соревнований — Фаза 3." />}
        />
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
