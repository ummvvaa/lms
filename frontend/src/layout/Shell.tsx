/** Каркас: боковая навигация по роли, шапка, область экрана. */
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useMaterialsState, useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { LOGO, SCHOOL_SHORT_NAME } from '../branding'
import { navFor } from './nav'
import FirstRun from '../components/FirstRun'
import LinkIdentityBanner from '../components/LinkIdentityBanner'
import Notifications from '../components/Notifications'
import ProfileMenu from '../components/ProfileMenu'
import SearchBox from '../components/SearchBox'
import './shell.css'

export default function Shell() {
  const { me } = useAuth()
  // три шага показываются сами при первом входе и вызываются повторно
  // отсюда: подсказка, которую нельзя вернуть, — одноразовая
  const [guide, setGuide] = useState(0)
  // раздел материалов есть не у всех: ученику его открывает отбор
  // в олимпиадную группу, и пункта меню у остальных быть не должно
  const materials = useMaterialsState()
  const prefs = useUpdatePreferences()
  // свёрнутость приходит с сервера, чтобы пережить смену устройства;
  // локальное состояние — для мгновенного отклика, сервер догоняет
  const [collapsed, setCollapsed] = useState(me?.sidebar_collapsed ?? false)
  if (!me) return null

  const items = navFor(me.role, me.can_see_whole_school, {
    materials: materials.data?.has_access ?? false,
    curator: materials.data?.is_curator ?? false,
  })

  const toggleSidebar = () => {
    const next = !collapsed
    setCollapsed(next)
    prefs.mutate({ sidebar_collapsed: next })
  }

  return (
    <div className={`shell${collapsed ? ' shell--collapsed' : ''}`}>
      <aside className="shell__nav">
        <div className="shell__brand">
          <img className="shell__logo" src={LOGO.sidebar} alt={SCHOOL_SHORT_NAME} />
          <span className="shell__brandname">{SCHOOL_SHORT_NAME}</span>
          <button
            className="shell__collapse"
            title={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
            aria-label={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
            onClick={toggleSidebar}
          >
            {collapsed ? '»' : '«'}
          </button>
        </div>
        <nav>
          {items.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              title={item.label}
              className={({ isActive }) => `navlink${isActive ? ' navlink--active' : ''}`}
            >
              <span className="navlink__icon">{item.icon}</span>
              <span className="navlink__label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="shell__main">
        <header className="shell__top">
          <div className="shell__topbrand">
            <img className="shell__toplogo" src={LOGO.header} alt="" />
            <div>
              <div className="shell__who">{me.full_name || me.email}</div>
              <div className="shell__role muted">
                {me.role_title}
                {me.domain_title ? ` · ведёт: ${me.domain_title}` : ''}
              </div>
            </div>
          </div>
          <SearchBox />

          <div className="shell__actions">
            <Notifications />
            <button className="btn btn-ghost btn-sm" onClick={() => setGuide((n) => n + 1)}>
              Как начать
            </button>
            <ProfileMenu />
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
