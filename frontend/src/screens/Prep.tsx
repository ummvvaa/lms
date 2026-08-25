/**
 * Центр подготовки: тренировки и пробные экзамены.
 *
 * Задания берутся из банка школы — выдуманных вопросов здесь быть не может.
 * Балл пробного не меняет текущий балл в профиле: его сверяет академический
 * директор. XP начисляется за прохождение, а не за результат (инвариант №12).
 */
import { useEffect, useRef, useState } from 'react'
import {
  useAnswerQuestion,
  useAttempts,
  useBankOverview,
  useFinishSession,
  useMockExams,
  useMyRuns,
  useStartMock,
  useStartPractice,
  type PrepQuestion,
  type PrepReview,
  type PrepSession,
} from '../api/hooks'
import ScoreTrend from '../components/ScoreTrend'
import Empty from '../components/Empty'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import './prep.css'
import { t } from '../i18n'

const SECTIONS: { value: string; title: string }[] = [
  { value: '', title: 'Все секции' },
  { value: 'listening', title: 'Listening' },
  { value: 'reading', title: 'Reading' },
  { value: 'writing', title: 'Writing' },
  { value: 'speaking', title: 'Speaking' },
  { value: 'math', title: 'Math' },
  { value: 'verbal', title: 'Verbal' },
]

const DIFFICULTIES: { value: string; title: string }[] = [
  { value: '', title: 'Любая сложность' },
  { value: 'easy', title: 'Простые' },
  { value: 'medium', title: 'Средние' },
  { value: 'hard', title: 'Сложные' },
]

/** Идёт сессия: вопросы по одному, ответ уходит сразу. */
function Runner({ session, onFinished }: { session: PrepSession; onFinished: (review: PrepReview) => void }) {
  const [index, setIndex] = useState(0)
  const [chosen, setChosen] = useState<Record<number, number>>({})
  const answer = useAnswerQuestion()
  const finish = useFinishSession()
  const startedAt = useRef(Date.now())
  const [left, setLeft] = useState<number | null>(
    session.time_limit_minutes ? session.time_limit_minutes * 60 : null,
  )

  const question: PrepQuestion | undefined = session.questions[index]
  const isLast = index >= session.questions.length - 1

  const complete = () =>
    finish.mutate(
      { session: session.id, seconds: Math.round((Date.now() - startedAt.current) / 1000) },
      { onSuccess: onFinished },
    )

  // время на мок ограничено: когда оно вышло, сессия закрывается сама
  useEffect(() => {
    if (left === null) return
    if (left <= 0) {
      complete()
      return
    }
    const timer = window.setTimeout(() => setLeft((value) => (value === null ? null : value - 1)), 1000)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left])

  if (!question) return <Loading />

  const pick = (optionId: number) => {
    setChosen((prev) => ({ ...prev, [question.answer_id]: optionId }))
    answer.mutate({ session: session.id, answer_id: question.answer_id, option: optionId, seconds: 0 })
  }

  return (
    <div className="card card-pad prep__runner">
      <div className="row-between prep__runhead">
        <span className="eyebrow">
          {session.mock ? session.mock : 'Тренировка'} · вопрос {index + 1} из {session.questions.length}
        </span>
        {left !== null && (
          <span className={`chip ${left < 60 ? 'chip-warn' : 'chip-mute'} num`}>
            {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
          </span>
        )}
      </div>

      <p className="prep__topic muted">
        {question.section} · {question.topic}
      </p>
      <p className="prep__text">{question.text}</p>

      <div className="prep__options">
        {question.options.map((option) => (
          <button
            key={option.id}
            className={`btn btn-ghost prep__option${chosen[question.answer_id] === option.id ? ' prep__option--picked' : ''}`}
            onClick={() => pick(option.id)}
          >
            <b>{option.letter}.</b> {option.text}
          </button>
        ))}
      </div>

      <div className="toolbar prep__nav">
        <button className="btn btn-ghost btn-sm" disabled={index === 0} onClick={() => setIndex(index - 1)}>
          {t('← Назад')}
        </button>
        <span className="toolbar__spacer" />
        {!isLast && (
          <button className="btn btn-primary btn-sm" onClick={() => setIndex(index + 1)}>
            {t('Дальше →')}
          </button>
        )}
        {isLast && (
          <button className="btn btn-primary btn-sm" onClick={complete} disabled={finish.isPending}>
            {finish.isPending ? 'Считаю…' : 'Завершить и посмотреть разбор'}
          </button>
        )}
      </div>
    </div>
  )
}

/** Разбор после сессии: что верно, почему, что подтянуть. */
function Review({ review, onAgain }: { review: PrepReview; onAgain: () => void }) {
  return (
    <div>
      <div className="card card-pad prep__result">
        <div className="row-between">
          <div>
            <span className="eyebrow">{t('Разбор ваших ответов')}</span>
            <p className="prep__score num">
              {review.correct} из {review.total} · {review.percent}%
            </p>
          </div>
          {review.score !== undefined && review.score !== null && (
            <div className="prep__mockscore">
              <b className="num">{review.score}</b>
              <span className="muted">{t('балл пробного')}</span>
            </div>
          )}
        </div>

        <p className="prep__recommend">{review.recommendation}</p>
        {review.note && <p className="muted prep__note">{review.note}</p>}

        {review.weak_topics.length > 0 && (
          <div className="prep__weak">
            <span className="eyebrow">{t('Темы, где больше всего ошибок')}</span>
            {review.weak_topics.map((topic) => (
              <div key={topic.topic} className="row-between prep__weakrow">
                <span>{topic.topic}</span>
                <span className="chip chip-warn num">
                  {topic.correct} из {topic.total}
                </span>
              </div>
            ))}
            <p className="muted prep__note">
              {t('По ним уже созданы задачи в роадмапе — их видно на главной.')}
            </p>
          </div>
        )}

        <button className="btn btn-primary btn-sm" onClick={onAgain}>
          {t('Ещё раз')}
        </button>
      </div>

      <h2 className="section">{t('Как отвечали')}</h2>
      <div className="grid grid--cards">
        {review.questions.map((question) => (
          <article
            key={question.answer_id}
            className={`card card-pad prep__answer${question.is_correct ? ' prep__answer--ok' : ' prep__answer--bad'}`}
          >
            <div className="row-between">
              <span className="muted prep__topic">{question.topic}</span>
              <span className={`chip ${question.is_correct ? 'chip-ok' : 'chip-warn'}`}>
                {question.is_correct ? 'верно' : 'мимо'}
              </span>
            </div>
            <p className="prep__text">{question.text}</p>
            <ul className="prep__answerlist">
              {question.options.map((option) => (
                <li
                  key={option.id}
                  className={
                    option.id === question.correct_option
                      ? 'prep__right'
                      : option.id === question.chosen
                        ? 'prep__wrong'
                        : undefined
                  }
                >
                  <b>{option.letter}.</b> {option.text}
                </li>
              ))}
            </ul>
            {question.explanation && <p className="prep__explain">{question.explanation}</p>}
            {question.source && <p className="muted prep__note">Источник: {question.source}</p>}
          </article>
        ))}
      </div>
    </div>
  )
}

/** Столько пройденных пробных показываем сразу. */
const VISIBLE_RUNS = 8

export default function Prep() {
  const [mode, setMode] = useState<'practice' | 'mocks'>('practice')
  const [showAllRuns, setShowAllRuns] = useState(false)
  const [examType, setExamType] = useState('IELTS')
  const [section, setSection] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [session, setSession] = useState<PrepSession | null>(null)
  const [review, setReview] = useState<PrepReview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const bank = useBankOverview()
  const mocks = useMockExams()
  const runs = useMyRuns()
  const attempts = useAttempts()
  const startPractice = useStartPractice()
  const startMock = useStartMock()

  const reset = () => {
    setSession(null)
    setReview(null)
    setError(null)
  }

  if (session && !review) {
    return (
      <div>
        <ScreenHead
          title={t('Центр подготовки')}
          subtitle={t('Отвечайте спокойно — разбор будет в конце.')}
        />
        <Runner
          session={session}
          onFinished={(result) => {
            setReview(result)
          }}
        />
      </div>
    )
  }

  if (review) {
    return (
      <div>
        <ScreenHead title={t('Центр подготовки')} subtitle={t('Что получилось и что стоит подтянуть.')} />
        <Review review={review} onAgain={reset} />
      </div>
    )
  }

  return (
    <div>
      <ScreenHead
        title={t('Центр подготовки')}
        subtitle={`В банке школы ${bank.data?.total ?? 0} заданий. Балл пробного сверяет академический директор.`}
      />

      <div className="toolbar">
        <button
          className={`tab${mode === 'practice' ? ' tab--active' : ''}`}
          onClick={() => setMode('practice')}
        >
          {t('Тренировка')}
        </button>
        <button className={`tab${mode === 'mocks' ? ' tab--active' : ''}`} onClick={() => setMode('mocks')}>
          {t('Пробные экзамены')}
        </button>
      </div>

      {error && <ErrorNote error={new Error(error)} />}

      {mode === 'practice' && (
        <div className="card card-pad">
          <span className="eyebrow">{t('Собрать тренировку')}</span>
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            <select className="input" value={examType} onChange={(e) => setExamType(e.target.value)}>
              {['IELTS', 'TOEFL', 'SAT', 'ACT'].map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <select className="input" value={section} onChange={(e) => setSection(e.target.value)}>
              {SECTIONS.map((row) => (
                <option key={row.value} value={row.value}>
                  {row.title}
                </option>
              ))}
            </select>
            <select className="input" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              {DIFFICULTIES.map((row) => (
                <option key={row.value} value={row.value}>
                  {row.title}
                </option>
              ))}
            </select>
            <button
              className="btn btn-primary btn-sm"
              disabled={startPractice.isPending}
              onClick={() => {
                setError(null)
                startPractice.mutate(
                  { exam_type: examType, section, difficulty, size: 10 },
                  {
                    onSuccess: setSession,
                    onError: (e) =>
                      setError(e instanceof Error ? e.message : 'Не удалось собрать тренировку'),
                  },
                )
              }}
            >
              {t('Начать')}
            </button>
          </div>
          {bank.data && bank.data.total === 0 && (
            <Empty
              title={t('Банк заданий пока пуст')}
              what={t('Тренировки заработают, когда в банке появятся задания.')}
              hint={t(
                'Задания заводит академический директор — тренировка собирается по секции и сложности.',
              )}
            />
          )}
        </div>
      )}

      {mode === 'mocks' && (
        <div className="grid grid--cards">
          {(mocks.data?.results ?? []).map((mock) => (
            <article key={mock.id} className="card card-pad">
              <b className="prep__mocktitle">{mock.title}</b>
              <p className="muted prep__note">
                {mock.exam_type} · {mock.time_limit_minutes} минут ·{' '}
                {mock.sections.map((s) => s.section_title).join(', ')}
              </p>
              <button
                className="btn btn-primary btn-sm"
                disabled={startMock.isPending}
                onClick={() => {
                  setError(null)
                  startMock.mutate(mock.id, {
                    onSuccess: setSession,
                    onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось начать пробный'),
                  })
                }}
              >
                {t('Пройти')}
              </button>
            </article>
          ))}
          {mocks.data?.results.length === 0 && (
            <Empty
              title={t('Пробных экзаменов пока нет')}
              what={t('Пробные составляет академический директор.')}
              hint={t('Это секции с ограничением по времени; результат ляжет в вашу динамику баллов.')}
            />
          )}
        </div>
      )}

      <h2 className="section">{t('Ваша динамика')}</h2>
      <div className="split">
        <div className="card card-pad">
          <ScoreTrend attempts={attempts.data?.results ?? []} examType="IELTS" />
        </div>
        <div className="card card-pad">
          <ScoreTrend attempts={attempts.data?.results ?? []} examType="SAT" />
        </div>
      </div>

      {(runs.data?.length ?? 0) > 0 && (
        <>
          <h2 className="section">{t('Пройденные пробные')}</h2>
          <div className="card card-pad">
            <table className="history">
              <tbody>
                {/* показываем последние: полный список за год не помещается
                    на экран и хоронит под собой всё остальное */}
                {(runs.data ?? []).slice(0, showAllRuns ? undefined : VISIBLE_RUNS).map((run) => (
                  <tr key={run.id}>
                    <td className="muted">{new Date(run.created_at).toLocaleDateString('ru')}</td>
                    <td style={{ fontWeight: 650 }}>{run.mock}</td>
                    <td className="num">{run.score ?? '—'}</td>
                    <td>
                      <span className={`chip ${run.counted_in_profile ? 'chip-ok' : 'chip-mute'}`}>
                        {run.counted_in_profile ? 'учтён в баллах' : 'ждёт сверки'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(runs.data ?? []).length > VISIBLE_RUNS && (
              <button
                className="btn btn-ghost btn-sm queue__more"
                onClick={() => setShowAllRuns(!showAllRuns)}
              >
                {showAllRuns
                  ? 'Показать только последние'
                  : `Показать все — ещё ${(runs.data ?? []).length - VISIBLE_RUNS}`}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
