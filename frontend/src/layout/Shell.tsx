/** Каркас: тёмное меню по роли на ноутбуке, тёмная полоса и нижний бар на телефоне, область экрана. */
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useJourney, useLocks, useMaterialsState, useNotifications, useUpdatePreferences } from '../api/hooks'
import { AssistantScreenProvider } from '../assistant/context'
import AssistantWidget from '../components/AssistantWidget'
import JobsPanel from '../components/JobsPanel'
import LockedScreen from '../components/LockedScreen'
import ErrorBoundary from '../components/ErrorBoundary'
import { useAuth } from '../auth/AuthContext'
import { LOGO, SCHOOL_MARK, SCHOOL_SHORT_NAME } from '../branding'
import Icon from './icons'
import MobileNav from './MobileNav'
import { NAV_GROUPS, navFor, tabsFor } from './nav'
import FirstRun from '../components/FirstRun'
import LinkIdentityBanner from '../components/LinkIdentityBanner'
import ProfileMenu from '../components/ProfileMenu'
import SearchBox from '../components/SearchBox'
import { Dialog, DialogContent, DialogTitle } from '../components/ui/dialog'
import './shell.css'
import { t } from '../i18n'
import CuratorCabinet from '../screens/curator/Cabinet'
import { readFlag } from '../lib/storage'
import { usePhone } from '../phone'

export default function Shell() {
  const { me } = useAuth()
  const location = useLocation()
  // три шага показываются сами при первом входе и вызываются повторно
  // из меню пользователя: подсказка, которую нельзя вернуть, — одноразовая
  const [guide, setGuide] = useState(0)
  // раздел материалов есть не у всех: ученику его открывает отбор
  // в олимпиадную группу, и пункта меню у остальных быть не должно
  const materials = useMaterialsState()
  // замки разделов ученика: раздел, который откроется после его шага,
  // показывается с объяснением, а не пустым экраном
  const locks = useLocks(me?.role === 'student')
  // «Мой путь» уходит из меню, когда все пять шагов пройдены:
  // раздел, в котором больше нечего делать, не должен занимать строку.
  // Вернуть его можно из профиля — тогда он снова в меню
  const journey = useJourney(me?.role === 'student')
  // приватное окно и закрытые куки роняли весь каркас на чтении хранилища
  const showJourney = readFlag('journey.pinned')
  // непрочитанное у пункта — число в пилюле: считается по адресам
  // уведомлений, а не по отдельному счётчику на каждый раздел
  const notifications = useNotifications()
  const prefs = useUpdatePreferences()
  // свёрнутость приходит с сервера, чтобы пережить смену устройства;
  // локальное состояние — для мгновенного отклика, сервер догоняет
  const [collapsed, setCollapsed] = useState(me?.sidebar_collapsed ?? false)
  // поиск: на ноутбуке — окно, которое открывают иконка в строке логотипа
  // и Ctrl+K; на телефоне поле раскрывается в самой полосе сверху
  const [searchOpen, setSearchOpen] = useState(false)
  // помощник: на телефоне плавающей кнопки нет — она накрывала правые
  // кнопки строк в любом месте прокрутки; герб живёт в полосе сверху,
  // а окно то же самое
  const phone = usePhone()
  const [assistantOpen, setAssistantOpen] = useState(false)
  // шторка со всеми разделами на телефоне: её открывают «Меню» сверху и «Ещё» снизу
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!me) return null

  let items = navFor(me.role, me.can_see_whole_school, {
    materials: materials.data?.has_access ?? false,
    curator: materials.data?.is_curator ?? false,
  })
  if (journey.data?.complete && !showJourney) items = items.filter((item) => item.path !== '/journey')

  const unreadLinks = (notifications.data?.rows ?? [])
    .filter((row) => !row.is_read && row.link)
    .map((row) => row.link as string)
  const unreadFor = (path: string) =>
    unreadLinks.filter((link) => link === path || link.startsWith(`${path}/`)).length
  const lockOf = (path: string) => (locks.data?.locks ?? []).find((row) => row.path === path && row.locked)
  const currentLock = lockOf(location.pathname)
  // группы с подписями: пустая группа не рисуется вовсе
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: items.filter((item) => item.group === group.key),
  })).filter((group) => group.items.length > 0)

  // заголовок тёмной полосы телефона — раздел, в котором человек сейчас;
  // у карточки ученика это «Ученики», у профиля — название роли
  const current = items
    .filter((item) => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]
  const title = current ? t(current.label) : me.role_title

  const toggleSidebar = () => {
    const next = !collapsed
    setCollapsed(next)
    prefs.mutate({ sidebar_collapsed: next })
  }
  const openGuide = () => setGuide((n) => n + 1)
  const user = { name: me.full_name || me.email, role: me.role_title }

  return (
    <AssistantScreenProvider>
      <div className={`shell${collapsed ? ' shell--collapsed' : ''}`}>
        {/* Тёмная полоса меню тянется во всю высоту экрана, а список внутри
            прокручивается сам: иначе на длинной странице колонка меню
            обрывалась, а карточка пользователя уезжала за нижний край */}
        <aside className="shell__nav">
          <div className="shell__navinner">
            <div className="shell__brand">
              <span className="shell__mark" aria-hidden="true">
                {SCHOOL_MARK}
              </span>
              <span className="shell__brandname">{SCHOOL_SHORT_NAME}</span>
              <button
                type="button"
                className="shell__iconbtn shell__navsearch"
                aria-label={t('Поиск')}
                title={`${t('Поиск')} (Ctrl+K)`}
                onClick={() => setSearchOpen(true)}
              >
                <Icon name="search" size={17} />
              </button>
              <button
                type="button"
                className="shell__iconbtn shell__collapse"
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
                  <span className="navgroup__label t-caps">{t(group.label)}</span>
                  {group.items.map((item) => {
                    const locked = lockOf(item.path)
                    const unread = locked ? 0 : unreadFor(item.path)
                    return (
                      <NavLink
                        key={item.path}
                        to={item.path}
                        title={locked ? t(locked.reason) : t(item.label)}
                        className={({ isActive }) =>
                          `navlink${isActive ? ' navlink--active' : ''}${locked ? ' navlink--locked' : ''}`
                        }
                      >
                        <Icon name={item.icon} size={18} />
                        <span className="navlink__label">{t(item.label)}</span>
                        {/* замок вместо пустоты: пункт остаётся видимым,
                          чтобы человек знал, что его ждёт */}
                        {locked && (
                          <span className="navlink__lock" aria-label={t('Пока закрыто')}>
                            <Icon name="lock" size={13} />
                          </span>
                        )}
                        {/* непрочитанное в разделе — число в пилюле справа */}
                        {unread > 0 && (
                          <span className="navlink__count num" title={t('Есть непрочитанное')}>
                            {unread}
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
            {/* Карточка пользователя закреплена внизу и открывает меню
                профиля вверх: там же уведомления и «Как начать» */}
            <div className="shell__user">
              <ProfileMenu user={user} onGuide={openGuide} side="top" />
            </div>
          </div>
        </aside>

        <div className="shell__main">
          {/* Тёмная полоса телефона — единственная шапка: на ноутбуке её нет,
              там поиск стоит в строке логотипа, а «Как начать» и уведомления
              лежат в меню пользователя. Слева «Меню» со всеми разделами,
              по центру раздел, справа поиск и аватар; раскрытый поиск
              занимает строку целиком, и та же кнопка его закрывает */}
          <header className={`shell__top${searchOpen ? ' shell__top--search' : ''}`}>
            <button
              type="button"
              className="shell__topbtn shell__menubtn"
              aria-label={t('Меню')}
              aria-haspopup="dialog"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <Icon name="menu" size={22} />
            </button>
            <span className="shell__title">{title}</span>
            {/* поиск по системе сужен сервером до того, что роли положено
                видеть: куратор находит только учеников своих групп */}
            {phone && searchOpen && (
              <div className="shell__search">
                <SearchBox focused onDone={() => setSearchOpen(false)} />
              </div>
            )}
            {/* помощник работает от домена: у куратора домена нет, и команды
                ему закрыты — кнопка открывала бы пустое окно с отказом */}
            {me.role !== 'curator' && (
              <button
                type="button"
                className="shell__topbtn shell__assistbtn"
                aria-label={t('Открыть помощника')}
                aria-expanded={assistantOpen}
                onClick={() => setAssistantOpen((open) => !open)}
              >
                <img src={LOGO.assistant} alt="" />
              </button>
            )}
            <button
              type="button"
              className="shell__topbtn shell__searchbtn"
              aria-label={searchOpen ? t('Закрыть поиск') : t('Поиск')}
              aria-expanded={searchOpen}
              onClick={() => setSearchOpen((open) => !open)}
            >
              <Icon name={searchOpen ? 'close' : 'search'} size={20} />
            </button>
            <ProfileMenu onGuide={openGuide} side="bottom" align="end" />
          </header>
          <main className="shell__screen">
            <LinkIdentityBanner />
            {/* три шага первого входа — только по «Как начать» из меню: подсказок
                на экранах нет (решение владельца, 27.09.2026) */}
            {guide > 0 && <FirstRun key={guide} role={me.role} forced />}
            {/* граница экрана: упавший раздел показывает сообщение,
                а меню остаётся на месте */}
            <ErrorBoundary scope="screen">
              {/* закрытый раздел не прячется: он виден приглушённым,
                  а сверху лежит объяснение и кнопка */}
              {currentLock ? (
                <LockedScreen lock={currentLock}>
                  <Outlet />
                </LockedScreen>
              ) : me.role === 'curator' ? (
                // кабинет куратора рисуется только по назначенным группам
                <CuratorCabinet>
                  <Outlet />
                </CuratorCabinet>
              ) : (
                <Outlet />
              )}
            </ErrorBoundary>
          </main>
        </div>

        {/* Телефон: вместо бокового меню — нижний бар из четырёх разделов
            роли и «Ещё» со всем меню. От 760px он не показывается */}
        <MobileNav
          tabs={tabsFor(me.role, items)}
          items={items}
          lockOf={lockOf}
          unreadFor={unreadFor}
          open={menuOpen}
          onOpenChange={setMenuOpen}
          title={me.role_title}
          subtitle={user.name}
        />

        {/* Окно поиска на ноутбуке: то же поле, что раньше стояло в шапке,
            только по вызову — иконкой в строке логотипа или Ctrl+K */}
        {!phone && (
          <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
            <DialogContent className="shell__searchdialog" showCloseButton={false}>
              <DialogTitle className="shell__searchtitle t-caps">{t('Поиск')}</DialogTitle>
              <div className="shell__search">
                <SearchBox focused onDone={() => setSearchOpen(false)} />
              </div>
            </DialogContent>
          </Dialog>
        )}

        {me.role !== 'curator' && (
          <AssistantWidget open={assistantOpen} onOpenChange={setAssistantOpen} fab={!phone} />
        )}
        {/* одна плашка на все долгие операции: у подбора была своя,
            у разбора файла не было никакой */}
        <JobsPanel />
      </div>
    </AssistantScreenProvider>
  )
}
