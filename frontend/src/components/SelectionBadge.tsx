/**
 * Плашка «идёт подбор» поверх любого экрана (фаза 40).
 *
 * Пока прогон считается, плашка показывает название и процент; по клику —
 * возврат к результату. Крестик прячет её до конца сессии — работа
 * в фоне продолжается.
 */
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useActiveSelection } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Button } from './ui/button'
import { t } from '../i18n'

export default function SelectionBadge() {
  const { me } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [hidden, setHidden] = useState(false)
  const active = useActiveSelection(me?.role === 'student')

  const run = active.data?.run
  if (!run || hidden || me?.role !== 'student') return null
  // на самом экране подбора плашка — дубль прогресса
  if (location.pathname.startsWith('/selection')) return null

  return (
    <div className="selbadge" role="status">
      <button className="selbadge__body" onClick={() => navigate(`/selection/${run.id}`)}>
        <span className="selbadge__title">{t('Подбор считается')}</span>
        <span className="muted selbadge__note">
          {run.major || t('все специальности')} · <b className="num">{run.progress}%</b>
        </span>
      </button>
      <Button variant="ghost" size="sm" aria-label={t('Скрыть плашку')} onClick={() => setHidden(true)}>
        ×
      </Button>
    </div>
  )
}
