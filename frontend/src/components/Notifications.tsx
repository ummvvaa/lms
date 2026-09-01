/**
 * Колокольчик внизу бокового меню: адресные уведомления.
 *
 * Текст приходит с сервера готовым — здесь он только показывается
 * (фаза 17). Ссылка ведёт внутрь интерфейса, наружу — никогда.
 *
 * Список всплывает в `Popover` из реестра — через портал, поверх
 * содержимого. До фазы 33 он был `position: absolute` внутри шапки
 * и, раскрываясь, раздвигал её: поиск, имя и кнопки разъезжались.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMarkNotificationsRead, useNotifications } from '../api/hooks'
import Icon from '../layout/icons'
import { t } from '../i18n'
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover'
import { Button } from './ui/button'

export default function Notifications() {
  const navigate = useNavigate()
  const { data } = useNotifications()
  const markRead = useMarkNotificationsRead()
  const [open, setOpen] = useState(false)

  const unread = data?.unread ?? 0
  const rows = data?.rows ?? []

  return (
    <Popover open={open} onOpenChange={setOpen}>
      {/* колокольчик без подписи: место в шапке дорогое, а иконка
          с числом непрочитанных читается быстрее слова */}
      <PopoverTrigger
        render={<Button variant="outline" size="icon-sm" className="notif__button" />}
        title={t('Уведомления')}
        aria-label={unread ? `${t('Уведомления')}, ${t('непрочитанных')}: ${unread}` : t('Уведомления')}
      >
        <Icon name="bell" size={17} />
        {unread > 0 && <span className="notif__dot num">{unread}</span>}
      </PopoverTrigger>

      {/* Панель поверх содержимого, ничего не сдвигает: шапка с заголовком
          и ссылкой «Прочитать все», ниже строки через тонкие линии —
          круглая иконка, текст, время серым, точка непрочитанного */}
      <PopoverContent align="start" side="top" sideOffset={8} className="notif__panel">
        <div className="notif__head">
          <span className="notif__title">{t('Уведомления')}</span>
          {unread > 0 && (
            <button type="button" className="notif__all" onClick={() => markRead.mutate(undefined)}>
              {t('Прочитать все')}
            </button>
          )}
        </div>
        {rows.length === 0 && <p className="muted notif__empty">{t('Пока ничего нового.')}</p>}
        <div className="notif__list">
          {rows.map((row) => (
            <button
              key={row.id}
              className={`notif__row${row.is_read ? '' : ' notif__row--new'}`}
              onClick={() => {
                markRead.mutate([row.id])
                setOpen(false)
                if (row.link) navigate(row.link)
              }}
            >
              <span className="notif__icon" aria-hidden="true">
                <Icon name="bell" size={14} />
              </span>
              <span className="notif__text">
                <span className="notif__what">{row.text}</span>
                <span className="muted notif__when">{new Date(row.created_at).toLocaleString('ru')}</span>
              </span>
              {!row.is_read && <span className="notif__new" aria-label={t('непрочитанное')} />}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
