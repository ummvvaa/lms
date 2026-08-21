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

export default function LinkIdentityBanner() {
  const { me } = useAuth()
  const link = useLinkIdentity()
  const [email, setEmail] = useState('')
  const [hidden, setHidden] = useState(false)

  if (!me || hidden) return null
  const hasPersonal = me.identities.some((identity) => identity.provider === 'email_link')
  if (hasPersonal || me.role !== 'student') return null

  if (link.isSuccess) {
    return (
      <div className="card card-pad banner banner--ok">
        Личная почта привязана — доступ сохранится и после выпуска.
      </div>
    )
  }

  return (
    <div className="card card-pad banner">
      <div className="banner__text">
        <b>Привяжите личную почту</b>
        <p className="muted banner__note">
          Школьный аккаунт после выпуска отключат. Личная почта — второй способ войти.
        </p>
      </div>
      <form
        className="banner__form"
        onSubmit={(e) => {
          e.preventDefault()
          link.mutate(email)
        }}
      >
        <input
          className="input"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@gmail.com"
        />
        <button className="btn btn-primary btn-sm" type="submit" disabled={link.isPending}>
          Привязать
        </button>
        <button className="btn btn-ghost btn-sm" type="button" onClick={() => setHidden(true)}>
          Позже
        </button>
      </form>
      {link.isError && <p className="chip chip-risk">Не удалось привязать эту почту</p>}
    </div>
  )
}
