/**
 * Вход по почте или логину и паролю.
 *
 * Логотип и название — над карточкой на полотне, в карточке только форма
 * (макет владельца, 11.10.2026): два поля с глазком у пароля, одна кнопка
 * во всю ширину, под ней тихая ссылка «Забыли пароль?»; мелкая «Я выпускник» —
 * под карточкой на полотне.
 * Справа вверху переключатель языка — тем же механизмом, что в оболочке:
 * выбор запоминается на устройстве. Слева внизу — адрес сайта.
 *
 * У 8–10 почты школы нет — они входят логином «имя.фамилия». Ссылку на
 * пароль им выдаёт куратор на экране; «Забыли пароль» работает, только
 * если к учётной записи привязана и подтверждена личная почта.
 * Регистрации самому себе нет: учётную запись заводит администратор.
 * Вторая дверь — одноразовая ссылка: для выпускников, у которых пароля нет.
 */
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { LOGO, SCHOOL_NAME } from '../branding'
import Backdrop from '../components/Backdrop'
import Field from '../components/Field'
import { Chip } from '../components/ui'
import { deviceLanguage, rememberLanguage, t, type Lang } from '../i18n'
import { Button } from '../components/ui/button'
import './login-layout.css'

type Mode = 'password' | 'reset' | 'link'

const LANGS: Lang[] = ['ru', 'kk', 'en']
// eslint-disable-next-line i18n-text -- короткие подписи языков на самих языках, не переводятся
const LANG_SHORT: Record<Lang, string> = { ru: 'Рус', kk: 'Қаз', en: 'Eng' }

function message(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : fallback
}

export default function Login() {
  const { login, requestPasswordReset, requestLink } = useAuth()
  const [mode, setMode] = useState<Mode>('password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const current = deviceLanguage()

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      if (mode === 'password') {
        await login(email, password)
      } else if (mode === 'reset') {
        await requestPasswordReset(email)
        setNote(t('Если такая почта известна системе, ссылка отправлена. Срок её действия указан в письме.'))
      } else {
        await requestLink(email)
        setNote(t('Если такая почта известна системе, ссылка отправлена.'))
      }
    } catch (e) {
      setError(message(e, mode === 'password' ? t('Не удалось войти') : t('Не удалось отправить ссылку')))
    } finally {
      setBusy(false)
    }
  }

  const switchMode = (next: Mode) => {
    setMode(next)
    setError(null)
    setNote(null)
  }

  return (
    <div className="login">
      <Backdrop />
      <div className="login__langs" role="group" aria-label={t('Язык')}>
        {LANGS.map((lang, index) => (
          <span key={lang} className="login__langitem">
            {index > 0 && <span className="login__langdot" aria-hidden="true">·</span>}
            <Button
              variant="link"
              size="sm"
              className={`login__lang${lang === current ? ' login__lang--on' : ''}`}
              aria-pressed={lang === current}
              lang={lang}
              onClick={() => rememberLanguage(lang)}
            >
              {LANG_SHORT[lang]}
            </Button>
          </span>
        ))}
      </div>

      <div className="login__brand">
        <img className="login__logo" src={LOGO.header} alt="" />
        <h1 className="login__title">{SCHOOL_NAME}</h1>
      </div>

      <div className="card card-pad card--beam login__card">
        {mode !== 'password' && (
          <p className="t-note login__sub">
            {mode === 'reset'
              ? `${t('Пришлём ссылку на смену пароля. Срок её действия указан в письме.')} ${t('Нет почты — попросите куратора выдать ссылку на пароль.')}`
              : t('Для выпускников: вход по ссылке на личную почту.')}
          </p>
        )}

        <form onSubmit={submit} className="login__form">
          {mode === 'password' ? (
            <Field name="email" id="email" label={t('Почта или логин')} value={email} onChange={setEmail} placeholder="ivanova@school.kz" autoComplete="username" required autoFocus />
          ) : (
            <Field kind="email" name="email" id="email" label={t('Почта')} value={email} onChange={setEmail} placeholder="ivanova@school.kz" autoComplete="username" required autoFocus />
          )}
          {mode === 'password' && <Field kind="password" name="password" id="password" label={t('Пароль')} value={password} onChange={setPassword} autoComplete="current-password" required />}
          <Button className="login__ms" type="submit" disabled={busy}>
            {mode === 'password' ? t('Войти') : t('Прислать ссылку')}
          </Button>
        </form>

        {note && <Chip tone="good" className="login__hint">{note}</Chip>}
        {error && <Chip tone="bad" className="login__hint">{error}</Chip>}

        {/* одна тихая ссылка без рамки и разделителя; вход выпускника — под карточкой */}
        <div className="login__links">
          {mode === 'password' ? (
            <Button variant="link" size="sm" className="login__link" onClick={() => switchMode('reset')}>
              {t('Забыли пароль?')}
            </Button>
          ) : (
            <Button variant="link" size="sm" className="login__link" onClick={() => switchMode('password')}>
              {t('Назад ко входу')}
            </Button>
          )}
        </div>
      </div>

      {/* вход выпускника — тихой ссылкой под карточкой, как в макете */}
      {mode === 'password' && (
        <Button variant="link" size="sm" className="login__link login__link--small login__grad" onClick={() => switchMode('link')}>
          {t('Я выпускник, у меня нет пароля')}
        </Button>
      )}

      <span className="login__host t-note">{window.location.host}</span>
    </div>
  )
}
