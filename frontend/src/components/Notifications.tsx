/**
 * Колокольчик в шапке: адресные уведомления.
 *
 * Текст приходит с сервера готовым — здесь он только показывается
 * (фаза 17). Ссылка ведёт внутрь интерфейса, наружу — никогда.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMarkNotificationsRead, useNotifications } from '../api/hooks'
import { t } from '../i18n'

export default function Notifications() {
  const navigate = useNavigate()
  const { data } = useNotifications()
  const markRead = useMarkNotificationsRead()
  const [open, setOpen] = useState(false)

  const unread = data?.unread ?? 0
  const rows = data?.rows ?? []

  return (
    <div className="notif">
      <button
        className="btn btn-ghost btn-sm notif__button"
        aria-label={unread ? `Уведомления, непрочитанных: ${unread}` : 'Уведомления'}
        onClick={() => setOpen((prev) => !prev)}
      >
        Уведомления
        {unread > 0 && <span className="notif__dot num">{unread}</span>}
      </button>

      {open && (
        <>
          <div className="notif__back" role="presentation" onClick={() => setOpen(false)} />
          <div className="notif__panel card">
            <div className="row-between notif__head">
              <span className="eyebrow">{t('Уведомления')}</span>
              {unread > 0 && (
                <button className="btn btn-ghost btn-sm" onClick={() => markRead.mutate(undefined)}>
                  {t('Отметить прочитанными')}
                </button>
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
          </div>
        </>
      )}
    </div>
  )
}
