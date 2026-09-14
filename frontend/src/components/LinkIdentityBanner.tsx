/**
 * Предложение привязать личную почту.
 *
 * Школьный аккаунт после выпуска отключат, и без второй идентичности
 * человек потеряет доступ. Поэтому предлагаем заранее и не навязчиво:
 * только на «Главной», а «Позже» закрывает насовсем — признак хранится
 * в профиле на сервере (фаза 75): закрыл на телефоне, не увидит
 * и на компьютере.
 */
import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useLinkIdentity, useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'
import Notice from './Notice'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

export default function LinkIdentityBanner() {
  const { me } = useAuth()
  const location = useLocation()
  const link = useLinkIdentity()
  const prefs = useUpdatePreferences()
  const [email, setEmail] = useState('')
  // мгновенный отклик на «Позже»; сервер догоняет через предпочтения
  const [hidden, setHidden] = useState(false)

  if (!me || hidden || me.link_identity_dismissed) return null
  const hasPersonal = me.identities.some((identity) => identity.provider === 'email_link')
  if (hasPersonal || me.role !== 'student') return null
  // одно место, а не каждый экран: баннер над каждым списком читается как шапка
  if (location.pathname !== '/dashboard') return null

  if (link.isSuccess) {
    return (
      <div className="card card-pad banner banner--ok">
        {t('Личная почта привязана — доступ сохранится и после выпуска.')}
      </div>
    )
  }

  return (
    <Notice tone="brand" className="card card-pad banner" summary={t('Привяжите личную почту')}>
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
            setHidden(true)
            prefs.mutate({ link_identity_dismissed: true })
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
    </Notice>
  )
}
