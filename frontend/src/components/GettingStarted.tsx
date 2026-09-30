/**
 * Панель «Начало работы» на дашборде.
 *
 * Галочки считает сервер по настоящему состоянию базы. Каждая строка
 * кликается и ведёт туда, где шаг и выполняется. Панель сворачивается
 * и исчезает совсем, когда выполнено всё: напоминать о сделанном — шум.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGettingStarted } from '../api/hooks'
import { usePhone } from '../phone'
import { Button } from './ui/button'
import { Chip } from './ui'
import { t } from '../i18n'
import { Row, Rows } from './patterns'

const FOLDED_KEY = 'getting-started-folded'

export default function GettingStarted() {
  const navigate = useNavigate()
  const phone = usePhone()
  // на телефоне панель свёрнута по умолчанию (фаза 75): шесть строк
  // с подсказками уводили содержимое дашборда за край экрана
  const [folded, setFolded] = useState(() => {
    const saved = localStorage.getItem(FOLDED_KEY)
    return saved === null ? phone : saved === '1'
  })
  const { data } = useGettingStarted()

  if (!data || data.total === 0 || data.complete) return null

  return (
    <section className="card card-pad start">
      <div className="row-between start__head">
        <div>
          <span className="eyebrow">
            {data.title}
            {phone && t(' — {done} из {total}', { done: data.done, total: data.total })}
          </span>
          {!(phone && folded) && (
            <p className="muted start__note">
              {t('Выполнено {done} из {total}. Панель исчезнет, когда всё будет готово.', { done: data.done, total: data.total })}
            </p>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const next = !folded
            setFolded(next)
            localStorage.setItem(FOLDED_KEY, next ? '1' : '0')
          }}
        >
          {folded ? t('Развернуть') : t('Свернуть')}
        </Button>
      </div>

      {!folded && (
        <Rows>
          {data.steps.map((step) => (
            <Row
              key={step.code}
              icon={step.done ? 'check' : 'checklist'}
              tone={step.done ? 'good' : 'neutral'}
              title={step.title}
              note={step.hint}
              right={
                step.count !== null ? (
                  <Chip size="sm" className="num">
                    {step.total !== null ? t('{count} из {total}', { count: step.count, total: step.total }) : step.count}
                  </Chip>
                ) : undefined
              }
              muted={step.done}
              onOpen={() => navigate(step.path)}
              openLabel={step.action || t('Открыть')}
            />
          ))}
        </Rows>
      )}
    </section>
  )
}
