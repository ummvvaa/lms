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

const FOLDED_KEY = 'getting-started-folded'

export default function GettingStarted() {
  const navigate = useNavigate()
  const [folded, setFolded] = useState(() => localStorage.getItem(FOLDED_KEY) === '1')
  const { data } = useGettingStarted()

  if (!data || data.total === 0 || data.complete) return null

  return (
    <section className="card card-pad start">
      <div className="row-between start__head">
        <div>
          <span className="eyebrow">{data.title}</span>
          <p className="muted start__note">
            Выполнено {data.done} из {data.total}. Панель исчезнет, когда всё будет готово.
          </p>
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => {
            const next = !folded
            setFolded(next)
            localStorage.setItem(FOLDED_KEY, next ? '1' : '0')
          }}
        >
          {folded ? 'Развернуть' : 'Свернуть'}
        </button>
      </div>

      {!folded && (
        <ul className="start__list">
          {data.steps.map((step) => (
            <li key={step.code}>
              <button
                className={`start__step${step.done ? ' start__step--done' : ''}`}
                onClick={() => navigate(step.path)}
              >
                <span className="start__check" aria-hidden="true">
                  {step.done ? '✓' : '○'}
                </span>
                <span className="start__body">
                  <span className="start__title">{step.title}</span>
                  <span className="muted start__hint">{step.hint}</span>
                </span>
                <span className="start__right">
                  {step.count !== null && (
                    <span className="chip chip-mute num">
                      {step.total !== null ? `${step.count} из ${step.total}` : step.count}
                    </span>
                  )}
                  {!step.done && step.action && <span className="start__action">{step.action} →</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
