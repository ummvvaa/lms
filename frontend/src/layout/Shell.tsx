/** Каркас: боковая навигация по роли, шапка, область экрана. */
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useLocks, useMaterialsState, useUpdatePreferences } from '../api/hooks'
import { AssistantScreenProvider } from '../assistant/context'
import AssistantWidget from '../components/AssistantWidget'
import JobsPanel from '../components/JobsPanel'
import LockedScreen from '../components/LockedScreen'
import ErrorBoundary from '../components/ErrorBoundary'
import { useAuth } from '../auth/AuthContext'
import { LOGO, SCHOOL_SHORT_NAME } from '../branding'
import Icon from './icons'
import { NAV_GROUPS, navFor } from './nav'
import FirstRun from '../components/FirstRun'
import LinkIdentityBanner from '../components/LinkIdentityBanner'
import Notifications from '../components/Notifications'
import ProfileMenu, { initials } from '../components/ProfileMenu'
import SearchBox from '../components/SearchBox'
import './shell.css'
import { t } from '../i18n'
import { Button } from '../components/ui/button'

export default function Shell() {
  const { me, logout } = useAuth()
  const location = useLocation()
  // три шага показываются сами при первом входе и вызываются повторно
  // отсюда: подсказка, которую нельзя вернуть, — одноразовая
  const [guide, setGuide] = useState(0)
  // раздел материалов есть не у всех: ученику его открывает отбор
  // в олимпиадную группу, и пункта меню у остальных быть не должно
  const materials = useMaterialsState()
  // замки разделов ученика: раздел, который откроется после его шага,
  // показывается с объяснением, а не пустым экраном (фаза 47)
  const locks = useLocks(me?.role === 'student')
  const prefs = useUpdatePreferences()
  // свёрнутость приходит с сервера, чтобы пережить смену устройства;
  // локальное состояние — для мгновенного отклика, сервер догоняет
  const [collapsed, setCollapsed] = useState(me?.sidebar_collapsed ?? false)
  if (!me) return null

  const items = navFor(me.role, me.can_see_whole_school, {
    materials: materials.data?.has_access ?? false,
    curator: materials.data?.is_curator ?? false,
  })
  const lockOf = (path: string) => (locks.data?.locks ?? []).find((row) => row.path === path && row.locked)
  const currentLock = lockOf(location.pathname)
  // группы с подписями: пустая группа не рисуется вовсе
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: items.filter((item) => item.group === group.key),
  })).filter((group) => group.items.length > 0)

  const toggleSidebar = () => {
    const next = !collapsed
    setCollapsed(next)
    prefs.mutate({ sidebar_collapsed: next })
  }

  return (
    <AssistantScreenProvider>
      <div className={`shell${collapsed ? ' shell--collapsed' : ''}`}>
        <aside className="shell__nav">
          <div className="shell__brand">
            <img className="shell__logo" src={LOGO.sidebar} alt={SCHOOL_SHORT_NAME} />
            <span className="shell__brandname">{SCHOOL_SHORT_NAME}</span>
            <button
              className="shell__collapse"
              title={collapsed ? t('Развернуть меню') : t('Свернуть меню')}
              aria-label={collapsed ? t('Развернуть меню') : t('Свернуть меню')}
              onClick={toggleSidebar}
            >
              <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} size={15} />
            </button>
          </div>
          <nav className="shell__menu">
            {groups.map((group) => (
              <div key={group.key} className="navgroup">
                <span className="navgroup__label">{t(group.label)}</span>
                {group.items.map((item) => {
                  const locked = lockOf(item.path)
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      title={locked ? t(locked.reason) : t(item.label)}
                      className={({ isActive }) =>
                        `navlink${isActive ? ' navlink--active' : ''}${locked ? ' navlink--locked' : ''}`
                      }
                    >
                      <span className="navlink__icon">
                        <Icon name={item.icon} />
                      </span>
                      <span className="navlink__label">{t(item.label)}</span>
                      {/* замок вместо пустоты: пункт остаётся видимым,
                          чтобы человек знал, что его ждёт (фаза 47) */}
                      {locked && (
                        <span className="navlink__lock" aria-label={t('Пока закрыто')}>
                          <Icon name="clock" size={13} />
                        </span>
                      )}
                    </NavLink>
                  )
                })}
              </div>
            ))}
          </nav>
          {/* блок пользователя закреплён внизу: кто вошёл и выход —
              всегда на одном месте, даже на длинном меню */}
          <div className="shell__user">
            <span className="shell__useravatar" aria-hidden="true">
              {initials(me.full_name, me.email)}
            </span>
            <span className="shell__usertext">
              <span className="shell__username">{me.full_name || me.email}</span>
              <span className="shell__userrole">{me.role_title}</span>
            </span>
            <button
              className="shell__logout"
              title={t('Выход')}
              aria-label={t('Выход')}
              onClick={() => void logout()}
            >
              <Icon name="logout" size={16} />
            </button>
          </div>
        </aside>

        <div className="shell__main">
          {/* Шапка в три колонки: слева кто вошёл, по центру поиск с потолком
              ширины, справа действия с одинаковыми отступами. Всплывающие
              списки идут через портал и положения ничего здесь не меняют */}
          <header className="shell__top">
            <div className="shell__topbrand">
              <img className="shell__toplogo" src={LOGO.header} alt="" />
              <div className="shell__topwho">
                <div className="shell__who">{me.full_name || me.email}</div>
                {/* одна строка — должность. Домен, который человек ведёт,
                    виден по составу меню, и повторять его здесь незачем */}
                <div className="shell__role muted">{me.role_title}</div>
              </div>
            </div>
            <div className="shell__search">
              <SearchBox />
            </div>
            <div className="shell__actions">
              <Button variant="outline" size="sm" onClick={() => setGuide((n) => n + 1)}>
                {t('Как начать')}
              </Button>
              <Notifications />
              <ProfileMenu />
            </div>
          </header>
          <main className="shell__screen">
            <LinkIdentityBanner />
            <FirstRun key={guide} role={me.role} forced={guide > 0} />
            {/* граница экрана: упавший раздел показывает сообщение,
                а меню и шапка остаются на месте */}
            <ErrorBoundary scope="screen">
              {currentLock ? <LockedScreen lock={currentLock} /> : <Outlet />}
            </ErrorBoundary>
          </main>
        </div>
        <AssistantWidget />
        {/* одна плашка на все долгие операции: у подбора была своя,
            у разбора файла не было никакой (фаза 47) */}
        <JobsPanel />
      </div>
    </AssistantScreenProvider>
  )
}
