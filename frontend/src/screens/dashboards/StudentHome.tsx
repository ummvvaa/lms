/**
 * Главная ученика в новом языке.
 *
 * Сверху четыре показателя с целью под числом, слева работа на сегодня:
 * уроки по звонкам, задачи с галочкой, вузы с разбором. Справа то, на что
 * ученик оглядывается: ближайшие даты, шаг пути, стипендии, незакрытые места.
 * Цветных полотен и карусели нет: пояснение — строкой, кнопка — в строке.
 *
 * Внутренних ярлыков здесь нет — их не отдаёт даже API (инвариант №7).
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMyLessons } from '../../api/academics'
import {
  useCalendar,
  useCenterExams,
  useGameState,
  useHomeCues,
  useJourney,
  useMyEssays,
  useMyProfile,
  useMyUniversities,
  usePortfolio,
  useSavedScholarships,
  useScholarshipOverview,
  useTaskStatus,
} from '../../api/hooks'
import { EVENT_KIND_TITLE, shortDate } from '../../components/CalendarCard'
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Checkbox } from '../../components/ui/checkbox'
import Progress from '../../components/Progress'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { MarkChip } from '../academics/shared'
import { ESSAY_TITLE, ESSAY_TONE } from '../essayStatus'
import { CabinetBoard } from './cabinet'
import { formatDate } from '../../lib/format'
import './student.css'


const MARK_WORDS: Record<string, string> = { present: 'был', absent: 'не был', late: 'опоздал', excused: 'уважительная' }

/** Уроки сегодня по звонкам: предмет, кабинет, учитель, моя отметка. */
function LessonsToday() {
  const navigate = useNavigate()
  const { data } = useMyLessons(todayAlmaty())
  if (!data) return null
  const rows = data.lessons
  const now = data.now_slot
  return (
    <DataCard
      title={t('Уроки сегодня')}
      count={rows.length || undefined}
      note={now ? `${t('идёт')} ${now} ${t('урок')}` : undefined}
      empty={rows.length === 0 && t('уроков сегодня нет')}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/schedule')}>
          {t('Расписание')}
        </Button>
      }
    >
      <Rows>
        {rows.map((lesson) => (
          <Row
            key={lesson.id}
            lead={<b className="num stu__slot">{lesson.slot}</b>}
            title={`${lesson.subject.title}${lesson.kind !== 'fo' ? ` · ${lesson.kind_label}` : ''}`}
            note={[lesson.bell, lesson.room, lesson.actual_teacher?.short ?? ''].filter(Boolean).join(' · ')}
            right={
              !lesson.is_live ? (
                <Chip tone="warn" size="sm">
                  {lesson.status_title}
                </Chip>
              ) : lesson.mine?.mark ? (
                <MarkChip mark={lesson.mine.mark} words={MARK_WORDS} size="sm" lateBy={lesson.mine.late_by} />
              ) : lesson.slot === now ? (
                <Chip tone="accent" size="sm">
                  {t('сейчас')}
                </Chip>
              ) : undefined
            }
            to={`/lessons/${lesson.id}`}
          />
        ))}
      </Rows>
    </DataCard>
  )
}

/** Задачи на сегодня с галочкой: выполненная уходит из списка после подтверждения. */
function TasksToday() {
  const navigate = useNavigate()
  const { data } = useGameState()
  const move = useTaskStatus()
  const [earned, setEarned] = useState<number | null>(null)
  useEffect(() => {
    if (earned === null) return
    const timer = window.setTimeout(() => setEarned(null), 4000)
    return () => window.clearTimeout(timer)
  }, [earned])
  if (!data) return null
  const rows = data.today
  const done = rows.filter((task) => task.status === 'done').length
  return (
    <DataCard
      title={t('Задачи на сегодня')}
      note={[rows.length ? `${done} ${t('из')} ${rows.length} ${t('сделано')}` : '', data.streak_phrase].filter(Boolean).join(' · ') || undefined}
      empty={rows.length === 0 && t('на сегодня задач нет')}
      emptyAction={
        <Button variant="secondary" size="sm" onClick={() => navigate('/roadmap')}>
          {t('Роадмап')}
        </Button>
      }
      right={
        <span className="stu__cardright">
          {earned !== null && (
            <Chip tone="good" size="sm">
              +{earned} XP
            </Chip>
          )}
          <Button variant="link" size="sm" onClick={() => navigate('/roadmap')}>
            {t('Все')}
          </Button>
        </span>
      }
    >
      <Rows>
        {rows.map((task) => (
          <Row
            key={task.id}
            lead={
              <Checkbox
                aria-label={task.title}
                checked={task.status === 'done'}
                disabled={move.isPending || task.status === 'done'}
                onCheckedChange={() => move.mutate({ id: task.id, status: 'done' }, { onSuccess: () => setEarned(task.xp) })}
              />
            }
            title={task.title}
            note={[task.university_name ?? '', task.days_left === null ? '' : task.days_left < 0 ? t('срок прошёл') : task.days_left === 0 ? t('сегодня') : `${t('до')} ${task.due_date ? formatDate(task.due_date) : ''}`].filter(Boolean).join(' · ')}
            right={
              task.days_left !== null && task.days_left <= 7 && task.status !== 'done' ? (
                <Chip tone={task.days_left < 0 ? 'bad' : 'warn'} size="sm">
                  {task.days_left < 0 ? t('просрочена') : task.days_left === 0 ? t('сегодня') : `${task.days_left} ${t('дн.')}`}
                </Chip>
              ) : undefined
            }
            muted={task.status === 'done'}
          />
        ))}
      </Rows>
    </DataCard>
  )
}

/** Готовность к подаче по доменам: домен без данных подписан, а не спрятан. */
function ReadinessBlock() {
  const { data } = useMyProfile()
  const readiness = data?.readiness
  if (!readiness) return null
  const rows = [
    ...readiness.parts.map((part) => ({ code: part.code, title: part.title, value: part.value as number | null })),
    ...readiness.skipped.map((part) => ({ code: part.code, title: part.title, value: null as number | null })),
  ]
  return (
    <DataCard
      title={t('Готовность к подаче')}
      note={readiness.weakest_title ? `${t('Больше всего сейчас даст')}: ${readiness.weakest_title}` : t('Из чего складывается ваш процент')}
      right={<b className="num t-value">{readiness.score}%</b>}
      empty={rows.length === 0 && t('данных пока нет — профиль ещё заполняется')}
    >
      <Rows>
        {rows.map((row) => (
          <Row
            key={row.code}
            title={row.title}
            note={row.value === null ? t('данных пока нет') : undefined}
            right={row.value === null ? undefined : <span className="prep__rowbar"><Progress percent={row.value} tone={row.code === readiness.weakest ? 'accent' : 'good'} /></span>}
          />
        ))}
      </Rows>
      {readiness.skipped.length > 0 && <p className="t-note">{t('Блоки без данных в процент не входят — он считается по тем, что заполнены.')}</p>}
    </DataCard>
  )
}

/** Подготовка: решённые задания, уровень и серия дней — по начислениям, без второго журнала. */
function PrepBlock() {
  const navigate = useNavigate()
  const game = useGameState()
  const exams = useCenterExams()
  const state = game.data
  const exam = exams.data?.exams?.[0]
  if (!state) return null
  const level = state.level_step ? Math.round((state.level_progress / state.level_step) * 100) : 0
  return (
    <DataCard
      title={exam ? `${t('Подготовка')} · ${exam.title}` : t('Центр подготовки')}
      note={exam && exam.bank_total > 0 ? `${t('Решено заданий')}: ${exam.solved} ${t('из')} ${exam.bank_total}` : t('Задания появятся, когда школа загрузит банк')}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/prep')}>
          {t('Продолжить')}
        </Button>
      }
    >
      <Rows>
        <Row
          icon="pencil"
          title={`${t('Уровень')} ${state.level}`}
          note={`${state.level_progress} / ${state.level_step} XP`}
          right={<span className="prep__rowbar"><Progress percent={level} label={false} /></span>}
        />
        <Row icon="flame" tone="accent" title={`${counted(state.streak_days, 'день|дня|дней')} ${t('подряд')}`} note={state.streak_phrase} />
      </Rows>
    </DataCard>
  )
}

/** Эссе: последние три с состоянием, новое — с экрана эссе. */
function EssaysBlock() {
  const navigate = useNavigate()
  const essays = useMyEssays()
  const rows = (essays.data?.results ?? []).slice(0, 3)
  return (
    <DataCard
      title={t('Мои эссе')}
      count={essays.data?.count || undefined}
      empty={rows.length === 0 && t('эссе ещё не заведено')}
      emptyAction={
        <Button variant="secondary" size="sm" onClick={() => navigate('/essays')}>
          {t('Новое эссе')}
        </Button>
      }
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/essays')}>
          {t('Все')}
        </Button>
      }
    >
      <Rows>
        {rows.map((essay) => {
          const last = essay.versions?.[0]
          return (
            <Row
              key={essay.id}
              icon="doc"
              title={essay.title}
              note={last ? `${formatDate(last.created_at)} · ${last.word_count} / ${essay.effective_word_limit} ${t('слов')}` : (essay.doc_type_name ?? t('черновик без версий'))}
              right={
                <Chip tone={ESSAY_TONE[essay.status]} size="sm">
                  {t(ESSAY_TITLE[essay.status])}
                </Chip>
              }
              onOpen={() => navigate('/essays')}
              openLabel={t('Открыть эссе')}
            />
          )
        })}
      </Rows>
    </DataCard>
  )
}

export default function StudentHome() {
  const navigate = useNavigate()
  const profile = useMyProfile()
  const portfolio = usePortfolio()
  const calendar = useCalendar()
  const journey = useJourney()
  const cues = useHomeCues()
  const universities = useMyUniversities()
  const scholarships = useScholarshipOverview()
  const saved = useSavedScholarships()

  if (profile.isLoading || portfolio.isLoading) return <Loading kind="cards" />
  if (profile.error) return <ErrorNote error={profile.error} />
  if (!profile.data) return null

  const exam = (profile.data.exam ?? {}) as Record<string, string | number | null>
  const documents = portfolio.data?.documents ?? []
  const documentsDone = documents.filter((doc) => doc.done).length
  const nearest = calendar.data?.nearest ?? null
  const today = calendar.data?.today ?? todayAlmaty()
  const upcoming = (calendar.data?.events ?? []).filter((event) => event.date >= today).slice(0, 6)
  const steps = journey.data?.steps ?? []
  const current = steps.find((step) => !step.done && !step.locked) ?? null
  const stepNumber = current ? steps.indexOf(current) + 1 : steps.length
  const unis = (universities.data ?? []).slice(0, 4)
  const cueRows = cues.data?.cues ?? []
  const score = (value: string | number | null | undefined) => (value === null || value === undefined || value === '' ? null : value)

  return (
    <div>
      <ScreenHead
        title={t('Главная')}
        subtitle={
          nearest
            ? nearest.days_left === 0
              ? `${nearest.title} — ${t('сегодня')}`
              : `${t('До ближайшего дедлайна')} ${counted(nearest.days_left, 'день|дня|дней')}: ${nearest.title}`
            : undefined
        }
      />

      <StatRow>
        <Kpi label="IELTS" value={score(exam.ielts_current)} none={t('нет')} note={score(exam.ielts_target) ? `${t('цель')} ${exam.ielts_target}` : t('цель не поставлена')} to="/my-data" />
        <Kpi label="SAT" value={score(exam.sat_current)} none={t('нет')} note={score(exam.sat_target) ? `${t('цель')} ${exam.sat_target}` : t('цель не поставлена')} to="/my-data" />
        <Kpi label={t('Портфолио')} value={portfolio.data ? `${portfolio.data.percent}%` : null} note={t('заполнено')} to="/my-data" />
        <Kpi label={t('Документы')} value={documents.length ? `${documentsDone} ${t('из')} ${documents.length}` : null} none={t('нет')} tone={documents.length && documentsDone < documents.length ? 'warn' : 'good'} to="/my-data?tab=documents" />
      </StatRow>

      <CabinetBoard
        cards={[
          { key: 'lessons', column: 'main', rows: 6, node: <LessonsToday /> },
          { key: 'tasks', column: 'main', rows: 5, node: <TasksToday /> },
          { key: 'readiness', column: 'main', rows: 5, node: <ReadinessBlock /> },
          {
            key: 'unis',
            column: 'main',
            rows: unis.length,
            folded: unis.length === 0,
            node: (
              <DataCard
                title={t('Мои вузы')}
                count={universities.data?.length || undefined}
                empty={unis.length === 0 && t('добавьте вуз — план соберётся сам')}
                emptyAction={
                  <Button variant="secondary" size="sm" onClick={() => navigate('/catalog')}>
                    {t('Открыть каталог')}
                  </Button>
                }
                right={
                  <Button variant="link" size="sm" onClick={() => navigate('/universities')}>
                    {t('Все')}
                  </Button>
                }
              >
                <Rows>
                  {unis.map((row) => {
                    const gap = row.breakdown.find((position) => !position.is_met && !position.is_unknown && position.gap_phrase)
                    return (
                      <Row
                        key={row.program}
                        icon="cap"
                        tone={row.is_open ? 'good' : 'neutral'}
                        title={row.university_name}
                        note={row.program_name}
                        right={
                          row.has_requirements ? (
                            <Chip tone={row.is_open ? 'good' : 'neutral'} size="sm">
                              {row.is_open ? t('проходите') : gap ? `${t('не хватает')} ${gap.gap_phrase}` : `${row.percent}%`}
                            </Chip>
                          ) : undefined
                        }
                        to="/universities"
                      />
                    )
                  })}
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'nearest',
            column: 'aside',
            rows: upcoming.length,
            folded: upcoming.length === 0,
            node: (
              <DataCard
                title={t('Ближайшее')}
                empty={upcoming.length === 0 && t('впереди пока пусто')}
                right={
                  <Button variant="link" size="sm" onClick={() => navigate('/calendar')}>
                    {t('Календарь')}
                  </Button>
                }
              >
                <Rows>
                  <ShowAll>
                    {upcoming.map((event, index) => (
                      <Row
                        key={`${event.date}-${index}`}
                        lead={<span className="stu__when num">{shortDate(event.date, today)}</span>}
                        title={event.title}
                        note={t(EVENT_KIND_TITLE[event.kind] ?? 'Событие')}
                        right={event.pending ? <Chip size="sm">{t('ждёт проверки')}</Chip> : undefined}
                        to={event.link}
                      />
                    ))}
                  </ShowAll>
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'journey',
            column: 'aside',
            rows: 1,
            folded: steps.length === 0,
            node: (
              <DataCard
                title={t('Мой путь')}
                note={current ? `${t('Шаг')} ${stepNumber} ${t('из')} ${steps.length}` : t('все шаги пройдены')}
                empty={steps.length === 0 && t('шаги появятся после первого входа')}
              >
                {current ? (
                  <Rows>
                    <Row
                      lead={<b className="num stu__slot">{stepNumber}</b>}
                      title={t(current.title)}
                      note={t(current.hint)}
                      acts={
                        <Button variant="secondary" size="sm" onClick={() => navigate(current.path)}>
                          {t('Продолжить')}
                        </Button>
                      }
                    />
                  </Rows>
                ) : (
                  <Rows>
                    <Row icon="check" tone="good" title={t('Путь пройден')} note={t('дальше работаете по плану')} to="/journey" />
                  </Rows>
                )}
              </DataCard>
            ),
          },
          {
            key: 'cues',
            column: 'aside',
            rows: cueRows.length,
            folded: cueRows.length === 0,
            node: (
              <DataCard title={t('Что закрыть')} empty={cueRows.length === 0 && t('незакрытых мест нет')}>
                <Rows>
                  {cueRows.map((cue) => (
                    <Row
                      key={cue.code}
                      icon="bulb"
                      tone="accent"
                      title={t(cue.title)}
                      note={t(cue.note)}
                      acts={
                        <Button variant="secondary" size="sm" onClick={() => navigate(cue.path)}>
                          {t(cue.action)}
                        </Button>
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
            ),
          },
          { key: 'prep', column: 'aside', rows: 2, node: <PrepBlock /> },
          { key: 'essays', column: 'aside', rows: 3, node: <EssaysBlock /> },
          {
            key: 'scholarships',
            column: 'aside',
            rows: 1,
            folded: !scholarships.data || scholarships.data.total === 0,
            node: (
              <DataCard title={t('Стипендии')} empty={(!scholarships.data || scholarships.data.total === 0) && t('в справочнике пока нет стипендий')}>
                <Rows>
                  <Row
                    icon="card"
                    title={`${counted(scholarships.data?.total ?? 0, 'стипендия|стипендии|стипендий')} ${t('в каталоге')}`}
                    note={saved.data?.count ? `${t('сохранено')} ${saved.data.count}` : t('сохранённых пока нет')}
                    to="/scholarships"
                  />
                </Rows>
              </DataCard>
            ),
          },
        ]}
      />
    </div>
  )
}
