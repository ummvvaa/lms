/**
 * Колокольчик в шапке: адресные уведомления.
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

      <PopoverContent align="end" sideOffset={8} className="notif__panel">
        <div className="row-between notif__head">
          <span className="t-card">{t('Уведомления')}</span>
          {unread > 0 && (
            <Button variant="outline" size="sm" onClick={() => markRead.mutate(undefined)}>
              {t('Отметить прочитанными')}
            </Button>
          )}
        </div>
        {rows.length === 0 && <p className="muted notif__empty">{t('Пока ничего нового.')}</p>}
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
            <span>{row.text}</span>
            <span className="muted notif__when">{new Date(row.created_at).toLocaleString('ru')}</span>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}
