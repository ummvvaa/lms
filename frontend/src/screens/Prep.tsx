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
  useCenterExams,
  useCenterSections,
  useCenterStatistics,
  useCenterTopics,
  useFinishSession,
  useMockExams,
  useMyRuns,
  useStartMock,
  useStartPractice,
  useTheory,
  type PrepQuestion,
  type PrepReview,
  type PrepSession,
} from '../api/hooks'
import Empty from '../components/Empty'
import { Bar, ErrorNote, Loading, Metric, MetricRow, ScreenHead, ScreenTabs } from '../components/ui'
import './prep.css'
import { t } from '../i18n'
import { NativeSelect } from '../components/ui/native-select'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

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
          <Badge variant={left < 60 ? 'warn' : 'mute'} className="num">
            {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
          </Badge>
        )}
      </div>

      <p className="prep__topic muted">
        {question.section} · {question.topic}
      </p>
      <p className="prep__text">{question.text}</p>

      <div className="prep__options">
        {question.options.map((option) => (
          <Button
            key={option.id}
            variant="outline"
            className={`prep__option${chosen[question.answer_id] === option.id ? ' prep__option--picked' : ''}`}
            onClick={() => pick(option.id)}
          >
            <b>{option.letter}.</b> {option.text}
          </Button>
        ))}
      </div>

      <div className="toolbar prep__nav">
        <Button variant="outline" size="sm" disabled={index === 0} onClick={() => setIndex(index - 1)}>
          {t('← Назад')}
        </Button>
        <span className="toolbar__spacer" />
        {!isLast && (
          <Button size="sm" onClick={() => setIndex(index + 1)}>
            {t('Дальше →')}
          </Button>
        )}
        {isLast && (
          <Button size="sm" onClick={complete} disabled={finish.isPending}>
            {finish.isPending ? 'Считаю…' : 'Завершить и посмотреть разбор'}
          </Button>
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
                <Badge variant="warn" className="num">
                  {topic.correct} из {topic.total}
                </Badge>
              </div>
            ))}
            <p className="muted prep__note">
              {t('По ним уже созданы задачи в роадмапе — их видно на главной.')}
            </p>
          </div>
        )}

        <Button size="sm" onClick={onAgain}>
          {t('Ещё раз')}
        </Button>
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
              <Badge variant={question.is_correct ? 'ok' : 'warn'}>
                {question.is_correct ? 'верно' : 'мимо'}
              </Badge>
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

const FORMATS = [
  { value: 'practice', title: 'Тренажёр', hint: 'Практика без ограничений' },
  { value: 'mocks', title: 'Пробник', hint: 'Проверка перед экзаменом, с временем' },
  { value: 'review', title: 'Работа над ошибками', hint: 'Разбор слабых мест' },
  { value: 'course', title: 'Курс', hint: 'Пошаговое обучение — скоро' },
] as const

type Format = (typeof FORMATS)[number]['value']

const DIFFICULTY_FILTERS = [
  { value: '', title: 'Любая сложность' },
  { value: 'easy', title: 'Простые' },
  { value: 'medium', title: 'Средние' },
  { value: 'hard', title: 'Сложные' },
]

/** Плитки семи экзаменов с прогрессом. */
function ExamPicker({ onPick }: { onPick: (exam: string) => void }) {
  const exams = useCenterExams()
  if (exams.isLoading) return <Loading kind="cards" />
  return (
    <div className="grid grid--cards">
      {(exams.data?.exams ?? []).map((exam) => (
        <button key={exam.exam_type} className="card card-pad prep__examtile" onClick={() => onPick(exam.exam_type)}>
          <b className="prep__mocktitle">{exam.title}</b>
          <p className="muted prep__note">
            {exam.bank_total === 0
              ? t('банк пока пуст')
              : `${t('решено')} ${exam.solved} ${t('из')} ${exam.bank_total}`}
          </p>
          {exam.bank_total > 0 && <Bar percent={Math.round((exam.solved / exam.bank_total) * 100)} />}
        </button>
      ))}
    </div>
  )
}

/** Тренажёр: секция → тема → фильтры → начать практику. */
function PracticePicker({
  exam,
  onStart,
}: {
  exam: string
  onStart: (session: PrepSession) => void
}) {
  const sections = useCenterSections(exam)
  const [section, setSection] = useState<string | null>(null)
  const [topic, setTopic] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const topics = useCenterTopics(exam, section)
  const startPractice = useStartPractice()
  const [error, setError] = useState<string | null>(null)

  const bankEmpty = (sections.data?.sections ?? []).every((s) => s.total === 0)
  if (sections.data && (sections.data.sections.length === 0 || bankEmpty)) {
    return (
      <Empty
        icon="pencil"
        title={t('Заданий по этому экзамену пока нет')}
        what={t('Тренажёр заработает, когда администратор загрузит банк.')}
        hint={t('Задания заводит академический директор, файл загружает администратор.')}
      />
    )
  }

  if (section === null) {
    return (
      <div className="grid grid--cards">
        {(sections.data?.sections ?? [])
          .filter((s) => s.total > 0)
          .map((s) => (
            <button key={s.section} className="card card-pad prep__examtile" onClick={() => setSection(s.section)}>
              <b className="prep__mocktitle">{s.title}</b>
              <p className="muted prep__note">
                {t('решено')} {s.solved} {t('из')} {s.total}
              </p>
              <Bar percent={Math.round((s.solved / s.total) * 100)} />
            </button>
          ))}
      </div>
    )
  }

  return (
    <div>
      <Button variant="ghost" size="sm" onClick={() => setSection(null)}>
        ← {t('К секциям')}
      </Button>
      {error && <ErrorNote error={new Error(error)} />}
      <div className="card card-pad">
        <span className="eyebrow">{t('Выберите тему')}</span>
        <div className="prep__topics">
          <button
            className={`prep__topic${topic === '' ? ' prep__topic--on' : ''}`}
            onClick={() => setTopic('')}
          >
            {t('Все темы')}
          </button>
          {(topics.data?.topics ?? []).map((row) => (
            <button
              key={row.topic}
              className={`prep__topic${topic === row.topic ? ' prep__topic--on' : ''}`}
              onClick={() => setTopic(row.topic)}
            >
              <span>{row.topic}</span>
              <span className="muted num">
                {row.solved}/{row.total}
              </span>
              <Bar percent={row.percent} />
            </button>
          ))}
        </div>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <NativeSelect value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            {DIFFICULTY_FILTERS.map((d) => (
              <option key={d.value} value={d.value}>
                {t(d.title)}
              </option>
            ))}
          </NativeSelect>
          <Button
            disabled={startPractice.isPending}
            onClick={() => {
              setError(null)
              startPractice.mutate(
                { exam_type: exam, section, topic, difficulty, size: 10 },
                {
                  onSuccess: onStart,
                  onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось собрать тренировку'),
                },
              )
            }}
          >
            {t('Начать практику')}
          </Button>
        </div>
      </div>
    </div>
  )
}

/** Статистика по экзамену: прогноз, серия, календарь, слабые темы, бейджи. */
function Statistics({ exam }: { exam: string }) {
  const stats = useCenterStatistics(exam)
  if (stats.isLoading) return <Loading kind="cards" />
  const data = stats.data
  if (!data) return null

  const days = Object.entries(data.calendar)
  const maxDay = Math.max(1, ...days.map(([, n]) => n))

  return (
    <div>
      <div className="card card-pad">
        <MetricRow>
          <Metric
            value={data.forecast.enough && data.forecast.score !== null ? data.forecast.score : '—'}
            label={t('Прогноз балла за тренировки')}
          />
          <Metric value={data.to_goal !== null ? data.to_goal : '—'} label={t('До цели')} />
          <Metric
            value={data.growth !== null ? `${data.growth > 0 ? '+' : ''}${data.growth}%` : '—'}
            label={t('Рост')}
            tone={data.growth !== null && data.growth >= 0 ? 'ok' : 'warn'}
          />
          <Metric value={data.streak} label={t('Серия дней')} tone="brand" />
        </MetricRow>
        {!data.forecast.enough && (
          <p className="muted prep__note">
            {t('Прогноз появится после')} {data.forecast.need_more}{' '}
            {t('ответов — это прогноз за тренировки, а не результат экзамена.')}
          </p>
        )}
      </div>

      <div className="split">
        <div className="card card-pad">
          <span className="eyebrow">{t('Активность за три месяца')}</span>
          <div className="prep__calendar">
            {days.length === 0 && <p className="muted">{t('Пока пусто — начните тренироваться.')}</p>}
            {days.map(([date, n]) => (
              <span
                key={date}
                className="prep__day"
                title={`${date}: ${n}`}
                style={{ opacity: 0.25 + (n / maxDay) * 0.75 }}
              />
            ))}
          </div>
        </div>
        <div className="card card-pad">
          <span className="eyebrow">{t('Слабые темы')}</span>
          {data.weak_topics.length === 0 && <p className="muted">{t('Слабых тем пока нет.')}</p>}
          <ul className="rows__list">
            {data.weak_topics.map((w) => (
              <li key={w.topic} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{w.topic}</span>
                </div>
                <Badge variant="warn" className="num">
                  {w.percent}%
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card card-pad">
        <span className="eyebrow">{t('Достижения')}</span>
        <div className="prep__badges">
          {data.achievements.map((badge) => (
            <div key={badge.kind} className={`prep__badge${badge.earned ? '' : ' prep__badge--locked'}`}>
              <span className="prep__badgetitle">
                {badge.title}
                {!badge.earned && <span className="muted"> · {t('закрыто')}</span>}
              </span>
              <span className="muted num">{badge.count > 0 ? `×${badge.count}` : ''}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/** Теория: уроки, сгруппированные по секциям, с уровнем и временем чтения. */
function Theory({ exam }: { exam: string }) {
  const theory = useTheory(exam)
  const [open, setOpen] = useState<number | null>(null)
  const rows = theory.data?.results ?? []
  if (rows.length === 0) {
    return (
      <Empty
        icon="book"
        title={t('Теории по этому экзамену пока нет')}
        what={t('Уроки ведёт академический директор.')}
        hint={t('Короткие уроки с уровнем и временем чтения появятся здесь.')}
      />
    )
  }
  const bySection = new Map<string, typeof rows>()
  for (const row of rows) {
    const key = row.section_title || t('Общее')
    bySection.set(key, [...(bySection.get(key) ?? []), row])
  }
  return (
    <div>
      {[...bySection.entries()].map(([section, lessons]) => (
        <div key={section} className="card card-pad" style={{ marginBottom: 12 }}>
          <span className="eyebrow">{section}</span>
          <ul className="rows__list">
            {lessons.map((lesson) => (
              <li key={lesson.id} className="rows__item prep__lesson">
                <button className="prep__lessonhead" onClick={() => setOpen(open === lesson.id ? null : lesson.id)}>
                  <span className="rows__label">{lesson.title}</span>
                  <span className="muted rows__note">
                    {lesson.level_title} · {lesson.reading_minutes} {t('мин')}
                  </span>
                </button>
                {open === lesson.id && (
                  <div className="prep__lessonbody">
                    <p className="prep__note">{lesson.body}</p>
                    {lesson.has_file && (
                      <Button variant="outline" size="sm" onClick={() => window.open(`/api/prep/theory/${lesson.id}/file/`)}>
                        {t('Открыть файл')}
                      </Button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export default function Prep() {
  const [exam, setExam] = useState<string | null>(null)
  const [format, setFormat] = useState<Format>('practice')
  const [tab, setTab] = useState<'prepare' | 'stats' | 'theory'>('prepare')
  const [session, setSession] = useState<PrepSession | null>(null)
  const [review, setReview] = useState<PrepReview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const mocks = useMockExams()
  const startMock = useStartMock()
  const runs = useMyRuns()

  const reset = () => {
    setSession(null)
    setReview(null)
    setError(null)
  }

  if (session && !review) {
    return (
      <div>
        <ScreenHead title={t('Центр подготовки')} subtitle={t('Отвечайте спокойно — разбор будет в конце.')} />
        <Runner session={session} onFinished={(result) => setReview(result)} />
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

  if (exam === null) {
    return (
      <div>
        <ScreenHead
          title={t('Центр подготовки')}
          subtitle={t('Выберите экзамен — по нему идёт подготовка, статистика и теория.')}
        />
        <ExamPicker onPick={setExam} />
      </div>
    )
  }

  const examMocks = (mocks.data?.results ?? []).filter((m) => m.exam_type === exam)

  return (
    <div>
      <ScreenHead
        title={`${t('Центр подготовки')} · ${exam}`}
        subtitle={t('Балл пробного сверяет академический директор.')}
        actions={
          <Button variant="outline" size="sm" onClick={() => setExam(null)}>
            {t('Сменить экзамен')}
          </Button>
        }
      />

      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'prepare', label: t('Подготовка') },
          { value: 'stats', label: t('Статистика') },
          { value: 'theory', label: t('Теория') },
        ]}
      />

      {error && <ErrorNote error={new Error(error)} />}

      {tab === 'prepare' && (
        <div>
          <div className="prep__formats">
            {FORMATS.map((f) => (
              <button
                key={f.value}
                className={`prep__format${format === f.value ? ' prep__format--on' : ''}`}
                onClick={() => setFormat(f.value)}
                disabled={f.value === 'course'}
              >
                <b>{t(f.title)}</b>
                <span className="muted">{t(f.hint)}</span>
              </button>
            ))}
          </div>

          {format === 'practice' && <PracticePicker exam={exam} onStart={setSession} />}
          {format === 'review' && <PracticePicker exam={exam} onStart={setSession} />}
          {format === 'course' && (
            <Empty icon="book" title={t('Курс скоро')} what={t('Пошаговое обучение появится позже.')} />
          )}
          {format === 'mocks' && (
            <div className="grid grid--cards">
              {examMocks.map((mock) => (
                <article key={mock.id} className="card card-pad">
                  <b className="prep__mocktitle">{mock.title}</b>
                  <p className="muted prep__note">
                    {mock.exam_type} · {mock.time_limit_minutes} {t('минут')} ·{' '}
                    {mock.sections.map((s) => s.section_title).join(', ')}
                  </p>
                  <Button
                    size="sm"
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
                  </Button>
                </article>
              ))}
              {examMocks.length === 0 && (
                <Empty
                  icon="pencil"
                  title={t('Пробных экзаменов пока нет')}
                  what={t('Пробные составляет академический директор.')}
                  hint={t('Это секции с ограничением по времени; результат ляжет в вашу динамику баллов.')}
                />
              )}
            </div>
          )}

          {(runs.data?.length ?? 0) > 0 && (
            <>
              <h2 className="section">{t('Пройденные пробные')}</h2>
              <div className="card card-pad">
                <table className="history">
                  <tbody>
                    {(runs.data ?? []).slice(0, 8).map((run) => (
                      <tr key={run.id}>
                        <td className="muted">{new Date(run.created_at).toLocaleDateString('ru')}</td>
                        <td style={{ fontWeight: 650 }}>{run.mock}</td>
                        <td className="num">{run.score ?? '—'}</td>
                        <td>
                          <Badge variant={run.counted_in_profile ? 'ok' : 'mute'}>
                            {run.counted_in_profile ? t('учтён в баллах') : t('ждёт сверки')}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'stats' && <Statistics exam={exam} />}
      {tab === 'theory' && <Theory exam={exam} />}
    </div>
  )
}
