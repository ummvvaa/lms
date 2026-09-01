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
import ProfileMenu from '../components/ProfileMenu'
import SearchBox from '../components/SearchBox'
import './shell.css'
import { t } from '../i18n'
import { Button } from '../components/ui/button'

export default function Shell() {
  const { me } = useAuth()
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
        {/* Полоса меню тянется во всю высоту страницы, а его содержимое
            прилипает к экрану: иначе на длинной странице колонка меню
            обрывалась белым, а блок пользователя уезжал за нижний край */}
        <aside className="shell__nav">
          <div className="shell__navinner">
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
                            <Icon name="lock" size={13} />
                          </span>
                        )}
                        {/* у раздела со своими внутренними экранами — стрелка */}
                        {!locked && item.nested && (
                          <span className="navlink__chev" aria-hidden="true">
                            <Icon name="chevronRight" size={13} />
                          </span>
                        )}
                      </NavLink>
                    )
                  })}
                </div>
              ))}
            </nav>
            {/* Блок пользователя закреплён внизу и он же открывает меню
              профиля вверх; рядом отдельной кнопкой колокольчик
              со счётчиком непрочитанных (фаза 48) */}
            <div className="shell__user">
              <ProfileMenu user={{ name: me.full_name || me.email, role: me.role_title }} />
              <Notifications />
            </div>
          </div>
        </aside>

        <div className="shell__main">
          {/* Шапка похудела до того, ради чего она есть: поиск с любого
              экрана и вызов подсказки первого входа. Кто вошёл, профиль
              и колокольчик уехали вниз бокового меню (фаза 48) —
              имя человека стояло на экране дважды. Название экрана
              и его действия живут в `ScreenHead` самого экрана */}
          <header className="shell__top">
            <div className="shell__search">
              <SearchBox />
            </div>
            <div className="shell__actions">
              <Button variant="outline" size="sm" onClick={() => setGuide((n) => n + 1)}>
                {t('Как начать')}
              </Button>
            </div>
          </header>
          <main className="shell__screen">
            <LinkIdentityBanner />
            <FirstRun key={guide} role={me.role} forced={guide > 0} />
            {/* граница экрана: упавший раздел показывает сообщение,
                а меню и шапка остаются на месте */}
            <ErrorBoundary scope="screen">
              {/* закрытый раздел не прячется: он виден приглушённым,
                  а сверху лежит объяснение и кнопка (фаза 48) */}
              {currentLock ? (
                <LockedScreen lock={currentLock}>
                  <Outlet />
                </LockedScreen>
              ) : (
                <Outlet />
              )}
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
