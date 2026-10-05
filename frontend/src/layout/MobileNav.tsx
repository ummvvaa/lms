/**
 * Нижний таб-бар и шторка со всеми разделами — навигация телефона.
 *
 * Тёмное меню на телефон не помещается: из 390 пикселей ширины 228
 * занимала бы полоса, в которую человек заглядывает раз в несколько
 * минут. Вместо неё четыре раздела внизу экрана — те, в которых роль
 * работает чаще всего (`TABS` в `nav.ts`), — и пятая кнопка «Ещё».
 *
 * «Ещё» открывает не остаток, а всё меню целиком теми же группами:
 * человек, который ищет раздел, не должен помнить, какие четыре
 * вынесены в бар. Ту же шторку открывает кнопка «Меню» в полосе сверху,
 * поэтому открыта она или нет — решает каркас, а не этот компонент.
 *
 * Подписи берутся из меню, а не придумываются заново: раздел, который
 * на ноутбуке называется «Роадмап», обязан называться так же и здесь,
 * иначе человек, который ходит и оттуда и отсюда, ищет несуществующее.
 * Сокращение задаётся полем `short` и только там, где означает то же.
 *
 * Замок и счётчик непрочитанного — те же, что в меню: закрытый раздел
 * виден с замком, а не пропадает.
 */
import { useRef, type PointerEvent as ReactPointerEvent } from 'react'
import { NavLink } from 'react-router'
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
  unreadFor,
  open,
  onOpenChange,
  title,
  subtitle,
}: {
  /** четыре раздела бара — уже отобранные по роли */
  tabs: NavItem[]
  /** все доступные разделы: шторка показывает их целиком */
  items: NavItem[]
  lockOf: (path: string) => { reason: string } | undefined
  /** сколько непрочитанных уведомлений ведут в раздел */
  unreadFor: (path: string) => number
  /** шторка открыта: её открывают и «Ещё» снизу, и «Меню» сверху */
  open: boolean
  onOpenChange: (open: boolean) => void
  /** заголовок шторки — роль, под ним имя вошедшего */
  title: string
  subtitle: string
}) {
  // палец, потянувший шторку вниз: закрываем, как закрыл бы жест
  const from = useRef<number | null>(null)

  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: items.filter((item) => item.group === group.key),
  })).filter((group) => group.items.length > 0)

  // счётчик на «Ещё»: разделы за пределами бара спрятаны в шторке,
  // и о новом в них иначе никак не узнать
  const unreadInRest = items
    .filter((item) => !tabs.some((tab) => tab.path === item.path))
    .reduce((sum, item) => sum + unreadFor(item.path), 0)

  const onDown = (event: ReactPointerEvent) => {
    from.current = event.clientY
  }
  const onUp = (event: ReactPointerEvent) => {
    if (from.current !== null && event.clientY - from.current > SWIPE_CLOSE) onOpenChange(false)
    from.current = null
  }

  return (
    <>
      <nav className="tabbar mobilenav" aria-label={t('Разделы')}>
        {tabs.map((item) => {
          const locked = lockOf(item.path)
          const unread = locked ? 0 : unreadFor(item.path)
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `tabbar__item${isActive ? ' tabbar__item--on' : ''}`}
              title={locked ? t(locked.reason) : t(item.label)}
            >
              <span className="tabbar__icon">
                <Icon name={locked ? 'lock' : item.icon} size={21} />
                {unread > 0 && (
                  <span className="tabbar__badge num" title={t('Есть непрочитанное')}>
                    {unread}
                  </span>
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
          onClick={() => onOpenChange(true)}
        >
          <span className="tabbar__icon">
            <Icon name="menu" size={21} />
            {unreadInRest > 0 && (
              <span className="tabbar__badge num" title={t('Есть непрочитанное')}>
                {unreadInRest}
              </span>
            )}
          </span>
          <span className="tabbar__label">{t('Ещё')}</span>
        </button>
      </nav>

      {/* Обычный лист снизу: закрывается по фону, по кнопке и свайпом вниз.
          Внутри — все разделы роли теми же группами, что в меню ноутбука */}
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" className="moresheet" onPointerDown={onDown} onPointerUp={onUp}>
          <span className="moresheet__grabber" aria-hidden="true" />
          <SheetHeader className="moresheet__head">
            <SheetTitle>{title}</SheetTitle>
            <span className="muted moresheet__sub">{subtitle}</span>
          </SheetHeader>

          <div className="moresheet__body">
            {groups.map((group) => (
              <div key={group.key} className="moresheet__group">
                <span className="moresheet__grouptitle t-caps">{t(group.label)}</span>
                {group.items.map((item) => {
                  const locked = lockOf(item.path)
                  const unread = locked ? 0 : unreadFor(item.path)
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      className={({ isActive }) => `moresheet__link${isActive ? ' moresheet__link--on' : ''}`}
                      title={locked ? t(locked.reason) : undefined}
                      onClick={() => onOpenChange(false)}
                    >
                      <span className="moresheet__icon">
                        <Icon name={item.icon} size={16} />
                      </span>
                      <span className="moresheet__label">{t(item.label)}</span>
                      {unread > 0 && <span className="moresheet__count num">{unread}</span>}
                      {locked ? (
                        <span className="moresheet__lock" aria-label={t('Пока закрыто')}>
                          <Icon name="lock" size={13} />
                        </span>
                      ) : (
                        <span className="moresheet__chev" aria-hidden="true">
                          <Icon name="chevronRight" size={16} />
                        </span>
                      )}
                    </NavLink>
                  )
                })}
              </div>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
