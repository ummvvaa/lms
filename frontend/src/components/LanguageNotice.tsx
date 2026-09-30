/**
 * Один раз после того, как язык сменила школа: ученику проставлен язык
 * его группы (`User.language_notice`). Текст — уже на новом языке: человек
 * видит, что случилось, и может вернуть свой язык здесь же, не ища профиль.
 * «Понятно» или смена языка закрывают плашку насовсем, на любом устройстве.
 */
import { useState } from 'react'
import { useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t, tk } from '../i18n'
import Notice from './Notice'
import { Button } from './ui/button'
import { languagesOf, offeredLanguage } from './ProfileMenu'

const NOW_ON = {
  ru: tk('Интерфейс теперь на русском языке.'),
  kk: tk('Интерфейс теперь на казахском языке.'),
  en: tk('Интерфейс теперь на английском языке.'),
} as const

export default function LanguageNotice() {
  const { me } = useAuth()
  const prefs = useUpdatePreferences()
  // мгновенный отклик; сервер снимает признак в том же запросе
  const [hidden, setHidden] = useState(false)
  if (!me || hidden || !me.language_notice) return null
  const current = offeredLanguage(me)
  const others = languagesOf(me).filter((item) => item.value !== current)

  return (
    <Notice tone="accent" className="card card-pad banner" summary={t(NOW_ON[current])}>
      <div className="banner__text">
        <b>{t(NOW_ON[current])}</b>
        <p className="muted banner__note">{t('Сменить язык — в профиле или по клику на своё имя.')}</p>
      </div>
      <div className="banner__form">
        {others.map((item) => (
          <Button
            key={item.value}
            variant="outline"
            size="sm"
            lang={item.value}
            onClick={() => {
              setHidden(true)
              prefs.mutate({ language: item.value })
            }}
          >
            {item.label}
          </Button>
        ))}
        <Button
          size="sm"
          onClick={() => {
            setHidden(true)
            prefs.mutate({ language_notice: false })
          }}
        >
          {t('Понятно')}
        </Button>
      </div>
    </Notice>
  )
}
