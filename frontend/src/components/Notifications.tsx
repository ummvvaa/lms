/**
 * Список адресных уведомлений — выдвижная панель, которую открывает
 * пункт «Уведомления» в меню пользователя.
 *
 * Текст приходит с сервера готовым — здесь он только показывается.
 * Ссылка ведёт внутрь интерфейса, наружу — никогда.
 *
 * Панель — `Sheet` из реестра: через портал, поверх содержимого, справа
 * на ноутбуке и снизу на телефоне. Отдельного колокольчика больше нет:
 * непрочитанное считается точкой на аватаре и числом в пункте меню.
 */
import { useNavigate } from 'react-router-dom'
import { useMarkNotificationsRead, useNotifications } from '../api/hooks'
import { t } from '../i18n'
import { usePhone } from '../phone'
import { Sheet, SheetContent, SheetTitle } from './ui/sheet'
import { Row, Rows } from './patterns'
import { Button } from './ui/button'
import { formatDateTime } from '../lib/format'

export default function Notifications({
  open,
  onOpenChange,
}: {
  /** открыта ли панель — решает меню пользователя, которое её вызывает */
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const phone = usePhone()
  const { data } = useNotifications()
  const markRead = useMarkNotificationsRead()

  const unread = data?.unread ?? 0
  const rows = data?.rows ?? []

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* Панель поверх содержимого, ничего не сдвигает: заголовок
          и ссылка «Прочитать все», ниже строки через тонкие линии —
          круглая иконка, текст, время серым, точка непрочитанного */}
      <SheetContent side={phone ? 'bottom' : 'right'} className="notif__sheet">
        <div className="notif__head">
          <SheetTitle className="notif__title">{t('Уведомления')}</SheetTitle>
          {unread > 0 && (
            <Button variant="link" size="sm" className="notif__all" onClick={() => markRead.mutate(undefined)}>
              {t('Прочитать все')}
            </Button>
          )}
        </div>
        {rows.length === 0 && <p className="muted notif__empty">{t('Пока ничего нового.')}</p>}
        <div className="notif__list">
          <Rows>
            {rows.map((row) => (
              <Row
                key={row.id}
                icon="bell"
                tone={row.is_read ? 'neutral' : 'accent'}
                title={row.text}
                note={formatDateTime(row.created_at)}
                right={!row.is_read ? <span className="notif__new" aria-label={t('непрочитанное')} /> : undefined}
                muted={row.is_read}
                onOpen={() => {
                  markRead.mutate([row.id])
                  onOpenChange(false)
                  if (row.link) navigate(row.link)
                }}
                openLabel={t('Открыть')}
              />
            ))}
          </Rows>
        </div>
      </SheetContent>
    </Sheet>
  )
}
