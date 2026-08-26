/**
 * Предложение привязать личную почту.
 *
 * Школьный аккаунт после выпуска отключат, и без второй идентичности
 * человек потеряет доступ. Поэтому предлагаем заранее и не навязчиво:
 * баннер закрывается и не возвращается в этой сессии.
 */
import { useState } from 'react'
import { useLinkIdentity } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

const DISMISS_KEY = 'lms.link-identity.dismissed'

export default function LinkIdentityBanner() {
  const { me } = useAuth()
  const link = useLinkIdentity()
  const [email, setEmail] = useState('')
  // «Позже» должно означать «позже», а не «до следующего перехода»:
  // компонент живёт в каркасе и перемонтируется на каждом экране
  const [hidden, setHidden] = useState(() => localStorage.getItem(DISMISS_KEY) === '1')

  if (!me || hidden) return null
  const hasPersonal = me.identities.some((identity) => identity.provider === 'email_link')
  if (hasPersonal || me.role !== 'student') return null

  if (link.isSuccess) {
    return (
      <div className="card card-pad banner banner--ok">
        {t('Личная почта привязана — доступ сохранится и после выпуска.')}
      </div>
    )
  }

  return (
    <div className="card card-pad banner">
      <div className="banner__text">
        <b>{t('Привяжите личную почту')}</b>
        <p className="muted banner__note">
          {t('Школьный аккаунт после выпуска отключат. Личная почта — второй способ войти.')}
        </p>
      </div>
      <form
        className="banner__form"
        onSubmit={(e) => {
          e.preventDefault()
          link.mutate(email)
        }}
      >
        <Input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@gmail.com"
        />
        <Button size="sm" type="submit" disabled={link.isPending}>
          {t('Привязать')}
        </Button>
        <Button
          variant="outline"
          size="sm"
          type="button"
          onClick={() => {
            localStorage.setItem(DISMISS_KEY, '1')
            setHidden(true)
          }}
        >
          {t('Позже')}
        </Button>
      </form>
      {link.isError && (
        <Badge variant="risk" className="badge--line">
          {t('Не удалось привязать эту почту')}
        </Badge>
      )}
      {email.trim() === '' && link.isIdle && (
        <p className="muted banner__note">{t('Укажите почту, которой пользуетесь вне школы.')}</p>
      )}
    </div>
  )
}
