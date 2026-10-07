/**
 * Правка учётной записи (фаза 67).
 *
 * До неё человека можно было завести и отключить, но не исправить:
 * владелец вписал при заведении почту в поле ФИО, и починить это
 * в интерфейсе было нечем. Роль правится в меню строки и сюда
 * не дублируется — второе место для одного действия расходится
 * с первым в первый же месяц.
 *
 * Почта — это логин, и об этом сказано прямо, до сохранения. После
 * смены почты прежняя ссылка-приглашение уже не придёт, поэтому рядом
 * стоит «Выслать письмо заново».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useUpdateUser, type ManagedUser } from '../api/hooks'
import { InviteUserDialog, LastUserMail, UserMailHistory } from '../components/UserMail'
import Modal from '../components/Modal'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { t } from '../i18n'
import { formatDateTime } from '../lib/format'

export default function EditUserDialog({ user, onClose }: { user: ManagedUser; onClose: () => void }) {
  const update = useUpdateUser()
  const [mailing, setMailing] = useState(false)
  const [fullName, setFullName] = useState(user.full_name)
  const [email, setEmail] = useState(user.email ?? '')
  const [moved, setMoved] = useState<string | null>(null)

  const emailChanged = email.trim().toLowerCase() !== (user.email ?? '').toLowerCase()
  const dirty = fullName !== user.full_name || emailChanged

  const save = () =>
    update.mutate(
      { id: user.id, full_name: fullName.trim(), email: email.trim() },
      {
        onSuccess: (data) => {
          if (data.login_changed) {
            setMoved(data.login_changed.detail)
          } else {
            toast.success(t('Учётная запись изменена'))
            onClose()
          }
        },
      },
    )

  if (mailing) return <InviteUserDialog user={{ ...user, email: email.trim() }} onClose={onClose} />

  return (
    <Modal title={t('Изменить учётную запись')} onClose={onClose}>
      <div className="euser">
        <span className="t-note">{user.password_state_title}</span>
        <LastUserMail user={user} />
        <span className="t-note">{user.last_login ? t('Последний вход: {date}', { date: formatDateTime(user.last_login) }) : t('Не входил ни разу')}</span>
        <label className="euser__field">
          <span className="eyebrow">{t('Имя и фамилия')}</span>
          <Input
            value={fullName}
            aria-label={t('Имя и фамилия')}
            onChange={(event) => setFullName(event.target.value)}
          />
        </label>

        <label className="euser__field">
          <span className="eyebrow">{t('Почта')}</span>
          <Input value={email} aria-label={t('Почта')} onChange={(event) => setEmail(event.target.value)} />
        </label>

        {emailChanged && (
          <p className="muted euser__warn">
            {t('Почта — это логин: после сохранения человек будет входить по новой почте.')}
          </p>
        )}

        {update.isError && <p className="euser__error">{update.error.message}</p>}

        {moved ? (
          <>
            <p className="euser__done">{moved}</p>
            <div className="ctask__actions">
              <span className="cfilters__spacer" />
              <Button
                size="sm"
                onClick={() => setMailing(true)}
              >
                {t('Выслать письмо заново')}
              </Button>
              <Button variant="outline" size="sm" onClick={onClose}>
                {t('Закрыть')}
              </Button>
            </div>
          </>
        ) : (
          <div className="ctask__actions">
            <span className="cfilters__spacer" />
            <Button size="sm" disabled={!dirty || update.isPending} onClick={save}>
              {t('Сохранить')}
            </Button>
            <Button variant="outline" size="sm" onClick={onClose}>
              {t('Отмена')}
            </Button>
          </div>
        )}
        <UserMailHistory id={user.id} />
      </div>
    </Modal>
  )
}
