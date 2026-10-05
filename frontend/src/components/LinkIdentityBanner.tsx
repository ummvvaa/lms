/**
 * Предложение привязать личную почту.
 *
 * Школьный аккаунт после выпуска отключат, и без второй идентичности
 * человек потеряет доступ. Почта работает только после подтверждения
 * письмом — иначе чужой адрес, набранный с опечаткой, стал бы входом. Поэтому предлагаем заранее и не навязчиво:
 * только на «Главной», а «Позже» закрывает насовсем — признак хранится
 * в профиле на сервере (фаза 75): закрыл на телефоне, не увидит
 * и на компьютере.
 */
import { useState } from 'react'
import { useLocation } from 'react-router'
import { useLinkIdentity, useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'
import Notice from './Notice'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { Chip } from './ui'

export default function LinkIdentityBanner() {
  const { me } = useAuth()
  const location = useLocation()
  const link = useLinkIdentity()
  const prefs = useUpdatePreferences()
  const [email, setEmail] = useState('')
  // нажали «Привязать» — теперь неверный адрес объясняется, а не молча не уходит
  const [tried, setTried] = useState(false)
  // мгновенный отклик на «Позже»; сервер догоняет через предпочтения
  const [hidden, setHidden] = useState(false)

  if (!me || hidden || me.link_identity_dismissed) return null
  const hasPersonal = me.identities.some((identity) => identity.provider === 'email_link')
  if (hasPersonal || me.role !== 'student') return null
  // одно место, а не каждый экран: баннер над каждым списком читается как шапка
  if (location.pathname !== '/dashboard') return null

  const typed = email.trim()
  const looksLikeEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(typed)

  if (link.isSuccess) {
    // письмо ушло — почта заработает после подтверждения по ссылке
    return <div className="card card-pad banner banner--ok">{link.data.detail}</div>
  }

  return (
    <Notice tone="accent" className="card card-pad banner" summary={t('Привяжите личную почту')}>
      <div className="banner__text">
        <b>{t('Привяжите личную почту')}</b>
        <p className="muted banner__note">
          {t('Школьный аккаунт после выпуска отключат. Личная почта — второй способ войти.')}
        </p>
      </div>
      {/* проверка своя, а не всплывающая подсказка браузера: её не замечали,
          и пустое поле «Привязать» молчало — ни запроса, ни объяснения */}
      <form
        className="banner__form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          setTried(true)
          if (looksLikeEmail) link.mutate(typed)
        }}
      >
        <Input
          type="email"
          value={email}
          aria-invalid={tried && !looksLikeEmail}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@gmail.com"
        />
        <Button size="sm" type="submit" disabled={link.isPending || typed === ''}>
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
      {tried && typed !== '' && !looksLikeEmail && <Chip tone="bad" className="badge--sentence">{t('Адрес почты пишется как name@gmail.com — проверьте «@» и домен')}</Chip>}
      {link.isError && (
        <Chip tone="bad" className="badge--sentence">
          {/* причина с сервера («адрес уже привязан к другой учётке») полезнее общих слов */}
          {link.error instanceof Error && link.error.message ? link.error.message : t('Не удалось привязать эту почту')}
        </Chip>
      )}
      {typed === '' && link.isIdle && (
        <p className="muted banner__note">{t('Укажите почту, которой пользуетесь вне школы.')}</p>
      )}
    </Notice>
  )
}
