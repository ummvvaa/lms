/** Письма для входа: результат отправки, история и явный повтор приглашения. */
import { useState } from 'react'
import { useInviteUsers, useUserMailHistory, type MailResult, type ManagedUser } from '../api/hooks'
import { t, tk } from '../i18n'
import { formatDateTime } from '../lib/format'
import Field from './Field'
import Modal from './Modal'
import { Chip, EmptyNote, ErrorNote, Loading, type Tone } from './ui'
import { Button } from './ui/button'
import './UserMail.css'

export function MailForceOption({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return <Field kind="checkbox" name="force_invite" label={t('Всё равно выслать')} checked={checked} onChange={onChange} />
}

/** HTTP 200 бывает и при отказе почты: показываем результат, а не обещание отправки. */
export function MailResultNotice({ result }: { result: MailResult }) {
  const failures = result.failures ?? []
  const tone: Tone = result.failed > 0 ? 'bad' : result.queued > 0 || result.skipped.length > 0 ? 'warn' : 'good'
  return (
    <div className="usermail__result" role="status" aria-live="polite">
      <Chip tone={tone} className="badge--sentence">{result.detail}</Chip>
      {failures.length + result.skipped.length > 0 && (
        <ul className="usermail__reasons">
          {[...failures, ...result.skipped].map((row, index) => <li key={`${row.email}-${index}`}>{row.email}: {row.reason}</li>)}
        </ul>
      )}
    </div>
  )
}

export function LastUserMail({ user }: { user: Pick<ManagedUser, 'last_mail_sent_at' | 'password_state'> }) {
  if (user.last_mail_sent_at) {
    return <span className="t-note">{t('Последнее письмо: {date}', { date: formatDateTime(user.last_mail_sent_at) })}</span>
  }
  if (user.password_state === 'invite_issued') return <span className="t-note">{t('Нет данных об отправке')}</span>
  return null
}

const MAIL_TONES: Record<string, Tone> = { sent: 'good', failed: 'bad', queued: 'warn', cancelled: 'neutral' }

export function UserMailHistory({ id }: { id: number }) {
  const history = useUserMailHistory(id)
  if (history.isLoading) return <Loading />
  if (history.error) return <ErrorNote error={history.error} />
  const rows = history.data?.rows ?? []
  return (
    <section className="usermail__history">
      <h3 className="t-card">{t('Последние письма')}</h3>
      {rows.length === 0 ? <EmptyNote what={tk('Записей об отправке пока нет')} /> : (
        <ol className="usermail__letters">
          {rows.map((row) => (
            <li key={row.id} className="usermail__letter">
              <div className="usermail__line">
                <b>{row.purpose_title}</b>
                <Chip tone={row.uncertain ? 'warn' : MAIL_TONES[row.status] ?? 'neutral'} size="sm">{row.status_title}</Chip>
              </div>
              <span>{row.address}</span>
              <span className="t-note">{row.sent_at
                ? t('Отправлено {date}', { date: formatDateTime(row.sent_at) })
                : t('Запрошено {date}', { date: formatDateTime(row.created_at) })}</span>
              {row.actor_name && <span className="t-note">{t('Запросил: {name}', { name: row.actor_name })}</span>}
              {row.error && <p className="usermail__error">{row.error}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export function InviteUserDialog({ user, onClose }: { user: ManagedUser; onClose: () => void }) {
  const invite = useInviteUsers()
  const [force, setForce] = useState(false)
  return (
    <Modal title={t('Выслать письмо заново')} onClose={onClose}>
      <div className="usermail">
        <p>{user.full_name || user.email}</p>
        <LastUserMail user={user} />
        <MailForceOption checked={force} onChange={setForce} />
        {invite.error && <ErrorNote error={invite.error} />}
        {invite.data && <MailResultNotice result={invite.data} />}
        <div className="acad__actions">
          <Button disabled={invite.isPending || !user.email} onClick={() => invite.mutate({ emails: [user.email ?? ''], force }, { onSuccess: () => setForce(false) })}>
            {t('Выслать письмо')}
          </Button>
          <Button variant="outline" onClick={onClose}>{t('Закрыть')}</Button>
        </div>
      </div>
    </Modal>
  )
}
