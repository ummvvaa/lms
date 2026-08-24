/**
 * Онбординг-квиз: восемь вопросов при первом входе.
 *
 * Прогресс сохраняется по шагам, а не в конце: ученик может выйти
 * на третьем вопросе и вернуться через неделю. Квиз можно отложить —
 * это не допрос.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAnswerOnboarding, useOnboarding, useSkipOnboarding } from '../api/hooks'
import { Bar, ErrorNote, Loading } from '../components/ui'
import './onboarding.css'
import { t } from '../i18n'

export default function Onboarding() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useOnboarding()
  const answer = useAnswerOnboarding()
  const skip = useSkipOnboarding()
  const [value, setValue] = useState('')
  const [problem, setProblem] = useState<string | null>(null)

  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const question = data.next
  const done = question === null

  const send = (raw: string) => {
    setProblem(null)
    answer.mutate(
      { question: question!.code, value: raw },
      {
        onSuccess: () => setValue(''),
        onError: (e) => setProblem(e instanceof Error ? e.message : 'Не получилось сохранить ответ'),
      },
    )
  }

  return (
    <div className="onboarding">
      <div className="card card-pad onboarding__card">
        <span className="eyebrow">{t('Знакомство')}</span>

        {done ? (
          <>
            <h1 className="onboarding__title">{t('Спасибо, этого достаточно')}</h1>
            <p className="muted onboarding__hint">
              {t(
                'Ваши ответы ушли директорам — они сверят их и уточнят, если понадобится. Дальше можно смотреть каталог и роадмап.',
              )}
            </p>
            <button className="btn btn-primary" onClick={() => navigate('/dashboard')}>
              {t('В кабинет')}
            </button>
          </>
        ) : (
          <>
            <div className="onboarding__progress">
              <div className="row-between onboarding__count">
                <span className="muted">
                  Вопрос {data.answered + 1} из {data.total}
                </span>
                <span className="muted num">{Math.round((data.answered / data.total) * 100)}%</span>
              </div>
              <Bar percent={(data.answered / data.total) * 100} />
            </div>

            <h1 className="onboarding__title">{question.title}</h1>
            <p className="muted onboarding__hint">{question.hint}</p>

            {question.kind === 'choice' && (
              <div className="onboarding__options">
                {question.options.map((option) => (
                  <button
                    key={option.value}
                    className="btn btn-ghost onboarding__option"
                    disabled={answer.isPending}
                    onClick={() => send(option.value)}
                  >
                    {option.title}
                  </button>
                ))}
              </div>
            )}

            {question.kind === 'bool' && (
              <div className="onboarding__options">
                <button className="btn btn-ghost onboarding__option" onClick={() => send('да')}>
                  {t('Да, есть')}
                </button>
                <button className="btn btn-ghost onboarding__option" onClick={() => send('нет')}>
                  {t('Пока нет')}
                </button>
              </div>
            )}

            {['text', 'number', 'decimal'].includes(question.kind) && (
              <form
                className="onboarding__form"
                onSubmit={(e) => {
                  e.preventDefault()
                  send(value)
                }}
              >
                <input
                  className="input"
                  inputMode={question.kind === 'text' ? 'text' : 'decimal'}
                  placeholder={question.placeholder}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  aria-label={question.title}
                />
                <button className="btn btn-primary" type="submit" disabled={answer.isPending}>
                  {t('Дальше')}
                </button>
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={answer.isPending}
                  onClick={() => send('')}
                >
                  {t('Ещё не сдавал')}
                </button>
              </form>
            )}

            {problem && <p className="chip chip-risk">{problem}</p>}

            <button
              className="btn btn-ghost btn-sm onboarding__skip"
              onClick={() => skip.mutate(undefined, { onSuccess: () => navigate('/dashboard') })}
            >
              {t('Пропустить и вернуться позже')}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
