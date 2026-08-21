/** Приземление одноразовой ссылки: гасим токен и заводим сессию. */
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function LinkLogin() {
  const [params] = useSearchParams()
  const { loginWithLink } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const attempted = useRef(false)

  useEffect(() => {
    const token = params.get('token')
    if (!token) {
      setError('В ссылке нет токена')
      return
    }
    // ссылка одноразовая — второй запрос её сожжёт впустую
    if (attempted.current) return
    attempted.current = true

    loginWithLink(token)
      .then(() => navigate('/dashboard', { replace: true }))
      .catch(() => setError('Ссылка недействительна или уже использована'))
  }, [params, loginWithLink, navigate])

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <h1 className="login__title">{error ? 'Не получилось' : 'Входим…'}</h1>
        {error && <p className="muted login__sub">{error}</p>}
      </div>
    </div>
  )
}
