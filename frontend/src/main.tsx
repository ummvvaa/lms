import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { applyTheme } from './theme'
import './styles/base.css'

// до загрузки профиля тема — как в системе; после входа применится выбор
applyTheme('system')

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
