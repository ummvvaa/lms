/**
 * Полоса «Шаг выполнен — следующий: …» (фаза 49).
 *
 * Раньше шаг пути уводил на свой экран, а чтобы перейти к следующему,
 * надо было вернуться на лестницу и найти там нужную строку. Теперь
 * следующий шаг догоняет человека там, где он закончил предыдущий:
 * лестница перестаёт быть обязательной точкой возврата.
 *
 * Закрывается крестиком и в этой сессии не возвращается: подсказка,
 * которую нельзя убрать, через день читается как часть шапки.
 */
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useJourney } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Icon from '../layout/icons'
import { Button } from './ui/button'
import { t } from '../i18n'

const HIDDEN_KEY = 'journey.stepbar.hidden'

function hiddenSteps(): string[] {
  try {
    return JSON.parse(sessionStorage.getItem(HIDDEN_KEY) ?? '[]') as string[]
  } catch {
    return []
  }
}

export default function StepDone() {
  const { me } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const journey = useJourney(me?.role === 'student')
  const [hidden, setHidden] = useState<string[]>(hiddenSteps)

  if (me?.role !== 'student' || !journey.data) return null
  const steps = journey.data.steps
  const index = steps.findIndex((step) => step.path === location.pathname)
  if (index < 0) return null
  const step = steps[index]
  if (!step.done || hidden.includes(step.code)) return null

  // следующий — первый невыполненный и незапертый после этого шага
  const next = steps.slice(index + 1).find((row) => !row.done && !row.locked)
  if (!next) return null

  const close = () => {
    const list = [...new Set([...hidden, step.code])]
    setHidden(list)
    sessionStorage.setItem(HIDDEN_KEY, JSON.stringify(list))
  }

  return (
    <div className="stepbar">
      <Icon name="check" size={15} />
      <span className="stepbar__text">
        {t('Шаг выполнен')} — {t('следующий')}: <b>{t(next.title)}</b>
      </span>
      <Button size="sm" onClick={() => navigate(next.path)}>
        {t(next.action)}
      </Button>
      <button type="button" className="stepbar__close" onClick={close} aria-label={t('Закрыть')}>
        <Icon name="close" size={14} />
      </button>
    </div>
  )
}
