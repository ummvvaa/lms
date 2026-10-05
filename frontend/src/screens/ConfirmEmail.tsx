/**
 * Приземление ссылки подтверждения личной почты.
 *
 * Токен гасится один раз — второй запрос сжёг бы его впустую. После
 * подтверждения по почте можно войти и восстановить пароль; входить
 * заново не нужно, если человек уже в системе.
 */
import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useConfirmIdentity } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'

export default function ConfirmEmail() {
  const [params] = useSearchParams()
  const { me } = useAuth()
  const confirm = useConfirmIdentity()
  const attempted = useRef(false)
  const token = params.get('token')

  useEffect(() => {
    if (!token || attempted.current) return
    attempted.current = true
    confirm.mutate(token)
  }, [token, confirm])

  const failed = !token || confirm.isError
  return (
    <div className="login">
      <div className="card card-pad login__card">
        <h1 className="login__title">
          {failed ? t('Не получилось') : confirm.isSuccess ? t('Почта подтверждена') : t('Проверяем ссылку…')}
        </h1>
        {failed && (
          <p className="muted login__sub">{token ? confirm.error?.message : t('В ссылке нет токена')}</p>
        )}
        {confirm.isSuccess && <p className="muted login__sub">{confirm.data.detail}</p>}
        {(failed || confirm.isSuccess) && (
          <p className="login__sub">
            <Link to={me ? '/profile' : '/login'}>{me ? t('Вернуться в профиль') : t('Перейти ко входу')}</Link>
          </p>
        )}
      </div>
    </div>
  )
}
