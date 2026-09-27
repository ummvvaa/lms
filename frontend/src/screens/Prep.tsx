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
  type PrepPassage,
  type PrepQuestion,
  type PrepReview,
  type PrepSession,
} from '../api/hooks'
import BadgesBlock from '../components/BadgesBlock'
import Empty from '../components/Empty'
import { Chip, counted, DataCard, EmptyNote, ErrorNote, Kpi, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Row, Rows, Segmented, StatRow } from '../components/patterns'
import DataTable from '../components/DataTable'
import Progress from '../components/Progress'
import './prep.css'
import './dashboards/student.css'
import { t } from '../i18n'
import { AnswerOption } from '../components/ui/answer-option'
import { Button } from '../components/ui/button'
import { Textarea } from '../components/ui/textarea'

/**
 * Страницы тренировки: вопросы к одному источнику — пассажу или аудио — идут
 * одной страницей, остальные по одному. Текст один, вопросов несколько, и читать
 * его заново перед каждым вопросом незачем.
 */
function pagesOf(questions: PrepQuestion[]): PrepQuestion[][] {
  const pages: PrepQuestion[][] = []
  for (const question of questions) {
    const last = pages[pages.length - 1]
    if (question.passage !== null && last && last[0].passage === question.passage) last.push(question)
    else pages.push([question])
  }
  return pages
}

/** Источник страницы: текст для чтения или аудио для аудирования. */
function PassagePanel({ passage }: { passage: PrepPassage }) {
  return (
    <section className="prep__passage" aria-label={passage.kind === 'listening' ? t('Аудио') : t('Текст')}>
      {passage.title && <h3 className="prep__passagetitle">{passage.title}</h3>}
      {passage.audio_url && (
        // аудио отдаётся после входа и только внутри своей тренировки
        <audio className="prep__audio" controls preload="metadata" src={passage.audio_url}>
          {t('Ваш браузер не воспроизводит аудио')}
        </audio>
      )}
      {passage.body && <div className="prep__passagebody">{passage.body}</div>}
    </section>
  )
}

const wordsIn = (text: string): number => text.trim().split(/\s+/).filter(Boolean).length

/** Идёт сессия: страница за страницей, ответ уходит сразу. */
function Runner({ session, onFinished }: { session: PrepSession; onFinished: (review: PrepReview) => void }) {
  const [index, setIndex] = useState(0)
  const [chosen, setChosen] = useState<Record<number, number>>(() =>
    Object.fromEntries(
      session.questions.filter((q) => q.chosen !== null).map((q) => [q.answer_id, q.chosen as number]),
    ),
  )
  const [texts, setTexts] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      session.questions.filter((q) => q.is_open).map((q) => [q.answer_id, q.answer_text ?? '']),
    ),
  )
  const answer = useAnswerQuestion()
  const finish = useFinishSession()
  const startedAt = useRef(Date.now())
  const [left, setLeft] = useState<number | null>(
    session.time_limit_minutes ? session.time_limit_minutes * 60 : null,
  )

  const pages = pagesOf(session.questions)
  const page = pages[index]
  const isLast = index >= pages.length - 1

  /** Открытые ответы страницы уходят на сервер при уходе с неё и перед завершением. */
  const saveTexts = async (questions: PrepQuestion[]) => {
    for (const question of questions.filter((q) => q.is_open))
      await answer.mutateAsync({
        session: session.id,
        answer_id: question.answer_id,
        text: texts[question.answer_id] ?? '',
        seconds: 0,
      })
  }

  const complete = async () => {
    await saveTexts(session.questions)
    finish.mutate(
      { session: session.id, seconds: Math.round((Date.now() - startedAt.current) / 1000) },
      { onSuccess: onFinished },
    )
  }

  // время на мок ограничено: когда оно вышло, сессия закрывается сама
  useEffect(() => {
    if (left === null) return
    if (left <= 0) {
      void complete()
      return
    }
    const timer = window.setTimeout(() => setLeft((value) => (value === null ? null : value - 1)), 1000)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left])

  if (!page) return <Loading />

  const pick = (question: PrepQuestion, optionId: number) => {
    setChosen((prev) => ({ ...prev, [question.answer_id]: optionId }))
    answer.mutate({ session: session.id, answer_id: question.answer_id, option: optionId, seconds: 0 })
  }

  const go = (next: number) => {
    void saveTexts(page)
    setIndex(next)
  }

  const passage = (session.passages ?? []).find((row) => row.id === page[0].passage)
  const first = session.questions.indexOf(page[0]) + 1
  const place =
    page.length > 1 ? `${t('вопросы')} ${first}–${first + page.length - 1}` : `${t('вопрос')} ${first}`

  return (
    <div className={`card card-pad prep__runner${passage ? ' prep__runner--wide' : ''}`}>
      <div className="row-between prep__runhead">
        <span className="eyebrow">
          {session.mock ? session.mock : t('Тренировка')} · {place} {t('из')} {session.questions.length}
        </span>
        {left !== null && (
          <Chip tone={left < 60 ? 'warn' : 'neutral'} className="num">
            {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
          </Chip>
        )}
      </div>

      {passage && <PassagePanel passage={passage} />}

      {page.map((question, order) => (
        <div key={question.answer_id} className="prep__question">
          <p className="prep__qtopic muted">
            {page.length > 1 ? `${first + order}. ` : ''}
            {question.section} · {question.topic}
          </p>
          <p className="prep__text">{question.text}</p>

          {question.is_open ? (
            // открытый ответ: вариантов нет, проверяет человек — оценка придёт в разбор
            <div className="prep__open">
              <Textarea
                rows={10}
                value={texts[question.answer_id] ?? ''}
                aria-label={t('Ваш ответ')}
                placeholder={
                  question.section === 'speaking'
                    ? t('Запишите тезисы своего устного ответа')
                    : t('Напишите ответ здесь')
                }
                onChange={(event) =>
                  setTexts((prev) => ({ ...prev, [question.answer_id]: event.target.value }))
                }
                onBlur={() => void saveTexts([question])}
              />
              <p className="muted prep__note">
                {question.word_limit
                  ? `${t('Слов:')} ${wordsIn(texts[question.answer_id] ?? '')} ${t('из')} ${question.word_limit}`
                  : `${t('Слов:')} ${wordsIn(texts[question.answer_id] ?? '')}`}
                {question.minute_limit ? ` · ${t('на ответ минут:')} ${question.minute_limit}` : ''}
                {' · '}
                {t('ответ проверит преподаватель')}
              </p>
            </div>
          ) : (
            /* Вариант ответа — свой элемент, а не кнопка реестра: правило
               реестра по двум атрибутам перебивало наш класс выбранного,
               и нажатие не отражалось на экране (та же поломка, что в квизе) */
            <div className="prep__options" role="radiogroup" aria-label={t('Варианты ответа')}>
              {question.options.map((option) => {
                const picked = chosen[question.answer_id] === option.id
                return (
                  <AnswerOption key={option.id} letter={option.letter} picked={picked} onPick={() => pick(question, option.id)}>
                      {option.text}
                  </AnswerOption>
                )
              })}
            </div>
          )}
        </div>
      ))}

      <div className="toolbar prep__nav">
        <Button variant="outline" size="sm" disabled={index === 0} onClick={() => go(index - 1)}>
          {t('← Назад')}
        </Button>
        <span className="toolbar__spacer" />
        {!isLast && (
          <Button size="sm" onClick={() => go(index + 1)}>
            {t('Дальше →')}
          </Button>
        )}
        {isLast && (
          <Button size="sm" onClick={() => void complete()} disabled={finish.isPending || answer.isPending}>
            {finish.isPending ? t('Считаю…') : t('Завершить и посмотреть разбор')}
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
            {(review.checked_by_machine ?? review.total) > 0 && (
              <p className="prep__score num">
                {review.correct} из {review.checked_by_machine ?? review.total} · {review.percent}%
              </p>
            )}
            {(review.open_waiting ?? 0) > 0 && (
              <p className="muted prep__note">
                {t('Открытых ответов ждут проверки преподавателя:')} {review.open_waiting}.{' '}
                {t('Оценка и комментарий появятся в этом разборе.')}
              </p>
            )}
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
                <Chip tone="warn" className="num">
                  {topic.correct} из {topic.total}
                </Chip>
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
        {review.questions.map((question) =>
          question.is_open ? (
            <OpenReview key={question.answer_id} question={question} />
          ) : (
            <article
              key={question.answer_id}
              className={`card card-pad prep__answer${question.is_correct ? ' prep__answer--ok' : ' prep__answer--bad'}`}
            >
              <div className="row-between">
                <span className="muted prep__topic">{question.topic}</span>
                <Chip tone={question.is_correct ? 'good' : 'warn'}>
                  {question.is_correct ? 'верно' : 'мимо'}
                </Chip>
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
          ),
        )}
      </div>
    </div>
  )
}

/** Открытый ответ в разборе: что написал ученик, критерии и проверка, когда она есть. */
function OpenReview({ question }: { question: PrepQuestion }) {
  return (
    <article className="card card-pad prep__answer">
      <div className="row-between">
        <span className="muted prep__topic">{question.topic}</span>
        {question.review ? (
          <Chip tone="good" className="num">
            {question.review.score !== null ? `${t('оценка')} ${question.review.score}` : t('проверено')}
          </Chip>
        ) : (
          <Chip tone="neutral">{t('ждёт проверки')}</Chip>
        )}
      </div>
      <p className="prep__text">{question.text}</p>
      <p className="prep__openanswer">{question.answer_text || t('Ответа нет')}</p>
      {question.review?.comment && <p className="prep__explain">{question.review.comment}</p>}
      {question.criteria && (
        <p className="muted prep__note">
          {t('Критерии оценки:')} {question.criteria}
        </p>
      )}
    </article>
  )
}

/** Столько пройденных пробных показываем сразу. */

const FORMATS = [
  { value: 'practice', title: 'Тренажёр', hint: 'Практика без ограничений', icon: 'pencil' },
  { value: 'mocks', title: 'Пробник', hint: 'Проверка перед экзаменом, с временем', icon: 'clock' },
  { value: 'review', title: 'Работа над ошибками', hint: 'Разбор слабых мест', icon: 'refresh' },
  { value: 'course', title: 'Курс', hint: 'Пошаговое обучение', icon: 'book' },
] as const

type Format = (typeof FORMATS)[number]['value']
type MyRun = NonNullable<ReturnType<typeof useMyRuns>['data']>[number]

/** Сколько вопросов в одной тренировке — число стоит и в подписи кнопки. */
const PRACTICE_SIZE = 10

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
  const rows = exams.data?.exams ?? []
  return (
    <div className="acad__cols">
      <div className="acad__stack">
        <DataCard title={t('Экзамены')} count={rows.length || undefined} empty={rows.length === 0 && t('академический директор ведёт их справочником — как появятся, раздел откроется')}>
          <Rows>
            {rows.map((exam) => (
              <Row
                key={exam.exam_type}
                lead={<b className="stu__slot">{exam.title.slice(0, 2)}</b>}
                title={exam.title}
                note={exam.bank_total === 0 ? t('банк пока пуст') : `${t('решено')} ${exam.solved} ${t('из')} ${exam.bank_total}`}
                right={exam.bank_total > 0 ? <span className="prep__rowbar"><Progress percent={Math.round((exam.solved / exam.bank_total) * 100)} /></span> : undefined}
                onOpen={() => onPick(exam.exam_type)}
                openLabel={t('Открыть')}
              />
            ))}
          </Rows>
        </DataCard>
      </div>
      <div className="acad__stack">
        <StatRow>
          <Kpi label={t('Экзаменов')} value={rows.length || null} none={t('нет')} />
          <Kpi label={t('Заданий в банке')} value={rows.reduce((sum, row) => sum + row.bank_total, 0) || null} none={t('нет')} />
        </StatRow>
      </div>
    </div>
  )
}

/** Тренажёр: секция → тема → фильтры → начать практику. */
function PracticePicker({ exam, onStart }: { exam: string; onStart: (session: PrepSession) => void }) {
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
      <DataCard title={t('Секции')}>
        <Rows>
          {(sections.data?.sections ?? [])
            .filter((s) => s.total > 0)
            .map((s) => (
              <Row key={s.section} icon="pencil" title={s.title} note={`${t('решено')} ${s.solved} ${t('из')} ${s.total}`} right={<span className="prep__rowbar"><Progress percent={Math.round((s.solved / s.total) * 100)} /></span>} onOpen={() => setSection(s.section)} openLabel={t('Открыть')} />
            ))}
        </Rows>
      </DataCard>
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
        <div className="acad__chips">
          <Button variant={topic === '' ? 'default' : 'outline'} size="sm" onClick={() => setTopic('')}>
            {t('Все темы')}
          </Button>
          {(topics.data?.topics ?? []).map((row) => (
            <Button key={row.topic} variant={topic === row.topic ? 'default' : 'outline'} size="sm" onClick={() => setTopic(row.topic)}>
              {row.topic} <span className="num"> · {row.solved}/{row.total}</span>
            </Button>
          ))}
        </div>
        <span className="eyebrow prep__filterhead">{t('Сложность')}</span>
        <Segmented
          value={difficulty}
          onChange={setDifficulty}
          label={t('Сложность')}
          items={DIFFICULTY_FILTERS.map((d) => ({ value: d.value, label: t(d.title) }))}
        />
        <div className="toolbar">
          <Button
            disabled={startPractice.isPending}
            onClick={() => {
              setError(null)
              startPractice.mutate(
                { exam_type: exam, section, topic, difficulty, size: PRACTICE_SIZE },
                {
                  onSuccess: onStart,
                  onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось собрать тренировку'),
                },
              )
            }}
          >
            {`${t('Начать практику')} · ${counted(PRACTICE_SIZE, ['вопрос', 'вопроса', 'вопросов'])}`}
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
  // блок достижений здесь же: прогресс по бейджам — часть статистики (фаза 46)

  const days = Object.entries(data.calendar)
  const maxDay = Math.max(1, ...days.map(([, n]) => n))

  return (
    <div>
      <BadgesBlock limit={3} />
      <div className="card card-pad">
        <StatRow>
          <Kpi
            value={data.forecast.enough && data.forecast.score !== null ? data.forecast.score : null}
            label={t('Прогноз балла за тренировки')}
          />
          <Kpi value={data.to_goal} label={t('До цели')} />
          <Kpi
            value={data.growth !== null ? `${data.growth > 0 ? '+' : ''}${data.growth}%` : null}
            label={t('Рост')}
            tone={data.growth !== null && data.growth >= 0 ? 'good' : 'warn'}
          />
          <Kpi value={data.streak} label={t('Серия дней')} tone="accent" />
        </StatRow>
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
            {days.length === 0 && <EmptyNote what={t('пока пусто — начните тренироваться.')} />}
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
          {data.weak_topics.length === 0 && <EmptyNote what={t('слабых тем пока нет.')} />}
          <ul className="rows__list">
            {data.weak_topics.map((w) => (
              <li key={w.topic} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{w.topic}</span>
                </div>
                <Chip tone="warn" className="num">
                  {w.percent}%
                </Chip>
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
        <div key={section} className="card card-pad mb-3">
          <span className="eyebrow">{section}</span>
          <ul className="rows__list">
            {lessons.map((lesson) => (
              <li key={lesson.id} className="rows__item prep__lesson">
                <Button variant="ghost" className="prep__lessonhead" onClick={() => setOpen(open === lesson.id ? null : lesson.id)}>
                  <span className="rows__label">{lesson.title}</span>
                  <span className="muted rows__note">
                    {lesson.level_title} · {lesson.reading_minutes} {t('мин')}
                  </span>
                </Button>
                {open === lesson.id && (
                  <div className="prep__lessonbody">
                    <p className="prep__note">{lesson.body}</p>
                    {lesson.has_file && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => window.open(`/api/prep/theory/${lesson.id}/file/`)}
                      >
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
        <ScreenHead
          title={t('Центр подготовки')}
        />
        <Runner session={session} onFinished={(result) => setReview(result)} />
      </div>
    )
  }
  if (review) {
    return (
      <div>
        <ScreenHead title={t('Центр подготовки')} />
        <Review review={review} onAgain={reset} />
      </div>
    )
  }

  if (exam === null) {
    return (
      <div>
        <ScreenHead
          title={t('Центр подготовки')}
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
          {/* Формат тренажёра — блок на цветном фоне: иконка, название,
              подпись и кружок выбора. Недоступный помечен «Скоро», а не
              просто выключен: выключенная кнопка без объяснения читается
              как поломка */}
          <div className="acad__toolbar">
            <Segmented<Format>
              value={format}
              onChange={setFormat}
              label={t('Формат тренажёра')}
              items={FORMATS.filter((f) => f.value !== 'course').map((f) => ({ value: f.value, label: t(f.title), icon: f.icon }))}
            />
            <span className="t-note">{`${t(FORMATS.find((f) => f.value === format)?.hint ?? '')} · ${t('Курс')}: ${t('скоро')}`}</span>
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
                        onError: (e) =>
                          setError(e instanceof Error ? e.message : 'Не удалось начать пробный'),
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
                <DataTable
                  columns={[
                    { key: 'date', title: t('Дата'), width: '20%', cell: (run: MyRun) => <span className="num">{new Date(run.created_at).toLocaleDateString('ru')}</span>, sortBy: (run: MyRun) => run.created_at },
                    { key: 'mock', title: t('Пробный'), width: '40%', cell: (run: MyRun) => <b>{run.mock}</b> },
                    { key: 'score', title: t('Балл'), width: '20%', align: 'right', cell: (run: MyRun) => <span className="num">{run.score ?? t('нет')}</span>, sortBy: (run: MyRun) => run.score },
                    { key: 'counted', title: '', width: '20%', cell: (run: MyRun) => <Chip tone={run.counted_in_profile ? 'good' : 'neutral'} size="sm">{run.counted_in_profile ? t('засчитан') : t('ждёт сверки')}</Chip> },
                  ]}
                  rows={(runs.data ?? []).slice(0, 8)}
                  rowKey={(run) => run.id}
                />
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
