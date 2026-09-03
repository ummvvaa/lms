/**
 * Нижний таб-бар и шторка «Ещё» — навигация телефона (фаза 51).
 *
 * Светлое меню с плитками на телефон не помещается: из 390 пикселей
 * ширины 248 занимала бы полоса, в которую человек заглядывает раз
 * в несколько минут. Вместо неё четыре раздела внизу экрана — те,
 * в которых роль работает чаще всего (`TABS` в `nav.ts`), — и пятая
 * кнопка «Ещё» со всем остальным теми же группами, что в меню.
 *
 * Подписи берутся из меню, а не придумываются заново: раздел, который
 * на ноутбуке называется «Роадмап», обязан называться так же и здесь,
 * иначе человек, который ходит и оттуда и отсюда, ищет несуществующее.
 * Сокращение задаётся полем `short` и только там, где означает то же.
 *
 * Замок и точка непрочитанного — те же, что в меню: закрытый раздел
 * виден с замком (фаза 47), а не пропадает.
 */
import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { NavLink } from 'react-router-dom'
import Notifications from '../components/Notifications'
import ProfileMenu from '../components/ProfileMenu'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../components/ui/sheet'
import { t } from '../i18n'
import Icon from './icons'
import { NAV_GROUPS, type NavItem } from './nav'

/** Насколько надо потянуть шторку вниз, чтобы она закрылась. */
const SWIPE_CLOSE = 60

export default function MobileNav({
  tabs,
  items,
  lockOf,
  hasUnread,
  user,
}: {
  /** четыре раздела бара — уже отобранные по роли */
  tabs: NavItem[]
  /** все доступные разделы: остальное уходит в шторку «Ещё» */
  items: NavItem[]
  lockOf: (path: string) => { reason: string } | undefined
  hasUnread: (path: string) => boolean
  user: { name: string; role: string }
}) {
  const [open, setOpen] = useState(false)
  // палец, потянувший шторку вниз: закрываем, как закрыл бы жест
  const from = useRef<number | null>(null)

  const rest = items.filter((item) => !tabs.some((tab) => tab.path === item.path))
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: rest.filter((item) => item.group === group.key),
  })).filter((group) => group.items.length > 0)

  // точка непрочитанного на «Ещё»: раздел спрятан в шторке, и о новом
  // в нём иначе никак не узнать
  const unreadInRest = rest.some((item) => hasUnread(item.path))

  const onDown = (event: ReactPointerEvent) => {
    from.current = event.clientY
  }
  const onUp = (event: ReactPointerEvent) => {
    if (from.current !== null && event.clientY - from.current > SWIPE_CLOSE) setOpen(false)
    from.current = null
  }

  return (
    <>
      <nav className="tabbar" aria-label={t('Разделы')}>
        {tabs.map((item) => {
          const locked = lockOf(item.path)
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `tabbar__item${isActive ? ' tabbar__item--on' : ''}`}
              title={locked ? t(locked.reason) : t(item.label)}
            >
              <span className="tabbar__icon">
                <Icon name={locked ? 'lock' : item.icon} size={19} />
                {!locked && hasUnread(item.path) && (
                  <span className="tabbar__dot" aria-label={t('Есть непрочитанное')} />
                )}
              </span>
              <span className="tabbar__label">{t(item.short ?? item.label)}</span>
            </NavLink>
          )
        })}

        <button
          type="button"
          className={`tabbar__item tabbar__more${open ? ' tabbar__item--on' : ''}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <span className="tabbar__icon">
            <Icon name="layers" size={19} />
            {unreadInRest && <span className="tabbar__dot" aria-label={t('Есть непрочитанное')} />}
          </span>
          <span className="tabbar__label">{t('Ещё')}</span>
        </button>
      </nav>

      {/* Обычный лист снизу: закрывается по фону, по кнопке и свайпом вниз.
          Внутри — остальные разделы, а под ними блок пользователя
          с колокольчиком: на телефоне бокового меню нет, и другого места
          у них не осталось */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="bottom" className="moresheet" onPointerDown={onDown} onPointerUp={onUp}>
          <span className="moresheet__grabber" aria-hidden="true" />
          <SheetHeader className="moresheet__head">
            <SheetTitle>{t('Все разделы')}</SheetTitle>
          </SheetHeader>

          <div className="moresheet__body">
            {groups.map((group) => (
              <div key={group.key} className="moresheet__group">
                <span className="moresheet__grouptitle">{t(group.label)}</span>
                {group.items.map((item) => {
                  const locked = lockOf(item.path)
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      className={({ isActive }) => `moresheet__link${isActive ? ' moresheet__link--on' : ''}`}
                      onClick={() => setOpen(false)}
                    >
                      <span className="moresheet__icon">
                        <Icon name={item.icon} size={17} />
                      </span>
                      <span className="moresheet__label">{t(item.label)}</span>
                      {locked && (
                        <span className="moresheet__lock" aria-label={t('Пока закрыто')}>
                          <Icon name="lock" size={13} />
                        </span>
                      )}
                      {!locked && hasUnread(item.path) && (
                        <span className="tabbar__dot" aria-label={t('Есть непрочитанное')} />
                      )}
                    </NavLink>
                  )
                })}
              </div>
            ))}
          </div>

          <div className="moresheet__user">
            <ProfileMenu user={user} />
            <Notifications />
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
