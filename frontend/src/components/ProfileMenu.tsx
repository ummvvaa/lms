/**
 * Меню по клику на аватар в правом верхнем углу.
 *
 * Сверху — кто вошёл, ниже — личные действия. Пункты «Язык» и «Тема»
 * появятся в фазе 24 вместе с самой возможностью: пункт меню без
 * действия хуже отсутствующего.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/** Инициалы для кружка-аватара: из имени, без имени — из почты. */
export function initials(name: string, email: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  if (parts.length === 1 && parts[0]) return parts[0].slice(0, 2).toUpperCase()
  return email.slice(0, 2).toUpperCase()
}

export default function ProfileMenu() {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  if (!me) return null

  const go = (path: string) => {
    setOpen(false)
    navigate(path)
  }

  return (
    <div className="pmenu">
      <button
        className="pmenu__avatar"
        aria-label="Меню профиля"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {initials(me.full_name, me.email)}
      </button>

      {open && (
        <>
          <div className="pmenu__back" role="presentation" onClick={() => setOpen(false)} />
          <div className="pmenu__panel card">
            <div className="pmenu__head">
              <b className="pmenu__name">{me.full_name || me.email}</b>
              <span className="muted pmenu__mail">{me.email}</span>
              <span className="muted pmenu__role">{me.role_title}</span>
            </div>
            <button className="pmenu__item" onClick={() => go('/profile')}>
              Профиль
            </button>
            <button className="pmenu__item" onClick={() => go('/profile#password')}>
              Смена пароля
            </button>
            <button className="pmenu__item" onClick={() => void logout()}>
              Выход
            </button>
          </div>
        </>
      )}
    </div>
  )
}
