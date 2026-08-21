/** Каркас приложения. Экраны и роутинг появляются в Фазе 2. */
export default function App() {
  return (
    <main className="shell">
      <h1>Платформа подготовки к поступлению</h1>
      <p className="muted">
        Фаза 1: схема базы и админка. Вход, роли и рабочие экраны — в следующих фазах.
      </p>
      <p className="muted">
        Админка Django: <a href="/admin/">/admin/</a>
      </p>
    </main>
  )
}
