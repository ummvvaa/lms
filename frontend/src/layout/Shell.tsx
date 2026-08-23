/** Каркас: боковая навигация по роли, шапка, область экрана. */
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { navFor } from './nav'
import FirstRun from '../components/FirstRun'
import LinkIdentityBanner from '../components/LinkIdentityBanner'
import './shell.css'

export default function Shell() {
  const { me, logout } = useAuth()
  // три шага показываются сами при первом входе и вызываются повторно
  // отсюда: подсказка, которую нельзя вернуть, — одноразовая
  const [guide, setGuide] = useState(0)
  if (!me) return null

  const items = navFor(me.role, me.can_see_whole_school)

  return (
    <div className="shell">
      <aside className="shell__nav">
        <div className="shell__brand">
          <span className="shell__mark">◆</span>
          <span>Платформа поступления</span>
        </div>
        <nav>
          {items.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `navlink${isActive ? ' navlink--active' : ''}`}
            >
              <span className="navlink__icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="shell__main">
        <header className="shell__top">
          <div>
            <div className="shell__who">{me.full_name || me.email}</div>
            <div className="shell__role muted">
              {me.role_title}
              {me.domain_title ? ` · ведёт: ${me.domain_title}` : ''}
            </div>
          </div>
          <div className="shell__actions">
            <button className="btn btn-ghost btn-sm" onClick={() => setGuide((n) => n + 1)}>
              Как начать
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => void logout()}>
              Выйти
            </button>
          </div>
        </header>
        <main className="shell__screen">
          <LinkIdentityBanner />
          <FirstRun key={guide} role={me.role} forced={guide > 0} />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
