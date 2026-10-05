import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { deviceLanguage, loadLanguage, setLanguage } from './i18n'
import { readText, writeText } from './lib/storage'
import { applyTheme } from './theme'
import './styles/base.css'

// до загрузки профиля тема — как в системе; после входа применится выбор
applyTheme('system')

// После выката старые куски сборки исчезают с сервера: открытая вкладка,
// переходя на экран, просила бы файл, которого уже нет. Перезагрузка берёт
// новую сборку. Не чаще раза в минуту — если файла нет и в новой, страница
// не уходит в бесконечную перезагрузку, а показывает ошибку экрана
window.addEventListener('vite:preloadError', (event) => {
  const key = 'build-reloaded-at'
  if (Date.now() - Number(readText(key) ?? 0) < 60_000) return
  writeText(key, String(Date.now()))
  event.preventDefault()
  window.location.reload()
})

function start() {
  createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      {/* внешняя граница: падение самого каркаса тоже показывает сообщение,
          а не пустую страницу */}
      <ErrorBoundary scope="app">
        <App />
      </ErrorBoundary>
    </React.StrictMode>,
  )
}

// Словарь языка этого устройства — отдельный кусок сборки и грузится до
// первой отрисовки: экран входа и каркас сразу на своём языке, русский не
// мелькает. У русского словаря нет — ждать нечего. Не загрузился (нет
// связи) — интерфейс всё равно открывается, по-русски
const lang = deviceLanguage()
loadLanguage(lang).then(
  () => {
    setLanguage(lang)
    start()
  },
  () => start(),
)
