/**
 * Главная ученика (фаза 48).
 *
 * Собрана по образцу: сверху полоса-подсказка о пропущенном шаге, ниже
 * два блока в ряд — карточка с призывом и календарь месяца с ближайшими
 * событиями, — дальше подготовка и эссе, список вузов и материалы школы.
 *
 * Лестница пяти шагов (фаза 37) больше не заменяет собой главную:
 * непройденный шаг приходит сюда призывом, а сама лестница осталась
 * отдельным экраном «Мой путь». Человек, зашедший в кабинет, должен
 * видеть свои дела, а не список того, чего он не сделал.
 *
 * Внутренних ярлыков здесь нет — их не отдаёт даже API (инвариант №7).
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useCalendar,
  useCenterExams,
  useGameState,
  useJourney,
  useMyEssays,
  useMyProfile,
  usePlans,
  useResources,
  type CalendarEvent,
  type JourneyStep,
} from '../../api/hooks'
import Icon from '../../layout/icons'
import TodayPanel from '../../components/TodayPanel'
import { Hero, Row, Rows, Tile, TipBar, type HeroTone } from '../../components/patterns'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import './home.css'

const MONTHS = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
]

const MONTH_NAMES = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
]

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const ESSAY_TONE: Record<string, 'mute' | 'warn' | 'risk' | 'ok'> = {
  draft: 'mute',
  review: 'warn',
  revision: 'risk',
  done: 'ok',
}
const ESSAY_TITLE: Record<string, string> = {
  draft: 'Черновик',
  review: 'На проверке',
  revision: 'Правки',
  done: 'Готово',
}

/** Дата события коротко: «15 окт.» или «Сегодня». */
function shortDate(iso: string, today: string): string {
  if (iso === today) return t('Сегодня')
  const date = new Date(iso)
  return `${date.getDate()} ${t(MONTHS[date.getMonth()])}`
}

function isoOf(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/**
 * Календарь месяца на цветной карточке: сетка дней, сегодняшний в кружке,
 * день с событием помечен точкой. Внутри белой панелью — ближайшие события.
 */
function CalendarBlock({ events, today }: { events: CalendarEvent[]; today: string }) {
  const navigate = useNavigate()
  const [shift, setShift] = useState(0)
  // пока ответ календаря не пришёл, `today` пустой: `new Date('')` даёт
  // Invalid Date, и сетка месяца падала на `Array(NaN)` — экран уходил
  // в границу ошибок ещё до первой отрисовки
  const parsed = new Date(today)
  const base = Number.isNaN(parsed.getTime()) ? new Date() : parsed
  const month = new Date(base.getFullYear(), base.getMonth() + shift, 1)
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const lead = (month.getDay() + 6) % 7
  const marked = new Set(events.map((event) => event.date))
  const cells: (number | null)[] = [
    ...Array<null>(lead).fill(null),
    ...Array.from({ length: daysInMonth }, (_, index) => index + 1),
  ]
  const nearest = events.slice(0, 4)

  return (
    <section className="hero hero--indigo home__cal">
      <div className="home__calhead">
        <b>
          {t(MONTH_NAMES[month.getMonth()])} {month.getFullYear()}
        </b>
        <button
          type="button"
          className="home__calnav"
          onClick={() => setShift((n) => n - 1)}
          aria-label={t('Предыдущий месяц')}
        >
          <Icon name="chevronLeft" size={14} />
        </button>
        <button
          type="button"
          className="home__calnav"
          onClick={() => setShift((n) => n + 1)}
          aria-label={t('Следующий месяц')}
        >
          <Icon name="chevronRight" size={14} />
        </button>
      </div>

      <div className="home__calgrid">
        {WEEKDAYS.map((day) => (
          <span key={day} className="home__calweekday">
            {t(day)}
          </span>
        ))}
        {cells.map((day, index) => {
          if (day === null) return <span key={`x${index}`} />
          const iso = isoOf(month.getFullYear(), month.getMonth(), day)
          return (
            <span
              key={iso}
              className={`num home__calday${iso === today ? ' home__calday--today' : ''}${
                marked.has(iso) ? ' home__calday--marked' : ''
              }`}
            >
              {day}
            </span>
          )
        })}
      </div>

      <div className="home__calpanel">
        <span className="home__panelhead">{t('Ближайшие события')}</span>
        {nearest.length === 0 && <p className="muted home__calempty">{t('Пока ничего не намечено.')}</p>}
        <Rows>
          {nearest.map((event, index) => (
            <Row
              key={`${event.date}-${index}`}
              lead={<span className="home__when">{shortDate(event.date, today)}</span>}
              title={event.title}
              right={event.pending ? <Badge variant="mute">{t('ждёт проверки')}</Badge> : undefined}
              onOpen={() => navigate(event.link)}
              openLabel={t('Открыть событие')}
            />
          ))}
        </Rows>
      </div>
    </section>
  )
}

/** Карточка призыва: текущий шаг пути или готовность, когда путь пройден. */
function CallToAction({ step, complete }: { step: JourneyStep | null; complete: boolean }) {
  const navigate = useNavigate()
  const tone: HeroTone = complete ? 'ink' : 'brand'
  if (complete || !step)
    return (
      <Hero
        compact
        className="home__cta"
        tone={tone}
        eyebrow={t('Путь пройден')}
        title={t('Дальше — по плану')}
        note={t('Все пять шагов позади. Ближайшие сроки и задачи ждут в плане поступления.')}
        figure="rings"
        action={<Button onClick={() => navigate('/plan')}>{t('Открыть план')}</Button>}
      />
    )
  return (
    <Hero
      compact
      className="home__cta"
      tone={tone}
      eyebrow={t('Следующий шаг')}
      title={t(step.title)}
      note={t(step.hint)}
      figure="rings"
      action={<Button onClick={() => navigate(step.path)}>{t(step.action)}</Button>}
    />
  )
}

/** Центр подготовки: уровень, серия по дням недели и кнопка продолжить. */
function PrepBlock() {
  const navigate = useNavigate()
  const game = useGameState()
  const exams = useCenterExams()
  const state = game.data
  const exam = exams.data?.exams?.[0]

  // Семь кружков по дням недели: отмечены те, в которые что-то было
  // засчитано. Считается по начислениям, а не по отдельному журналу
  // посещений — второго источника заводить незачем.
  const week = useMemo(() => {
    const active = new Set((state?.recent ?? []).map((row) => row.created_at.slice(0, 10)))
    const today = new Date()
    const monday = new Date(today)
    monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
    return Array.from({ length: 7 }, (_, index) => {
      const day = new Date(monday)
      day.setDate(monday.getDate() + index)
      const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
      return { iso, label: WEEKDAYS[index], done: active.has(iso) }
    })
  }, [state?.recent])

  const percent = state?.level_step ? Math.round((state.level_progress / state.level_step) * 100) : 0

  return (
    <section className="card card-pad card--accent card--teal home__prep">
      <header className="home__cardhead">
        <Tile icon="pencil" tone="teal" size="lg" />
        <span className="home__cardtitle">
          <b>{exam ? `${t('Подготовка')} · ${exam.title}` : t('Центр подготовки')}</b>
          <span className="muted">
            {exam && exam.bank_total > 0
              ? `${t('Решено заданий')}: ${exam.solved} ${t('из')} ${exam.bank_total}`
              : t('Задания появятся, когда школа загрузит банк')}
          </span>
        </span>
      </header>

      <div className="home__level">
        <span className="muted">
          {t('Уровень')} {state?.level ?? 1}
        </span>
        <b className="num">
          {state?.level_progress ?? 0} / {state?.level_step ?? 100}
        </b>
      </div>
      <div className="bar home__levelbar">
        <i style={{ width: `${percent}%`, background: 'var(--teal)' }} />
      </div>

      <div className="home__streak">
        <span className="home__streaktile">
          <Icon name="flame" size={16} />
          <b className="num">
            {state?.streak_days ?? 0} {t('дн.')}
          </b>
        </span>
        <span className="home__week">
          {week.map((day) => (
            <span
              key={day.iso}
              className={`home__daydot${day.done ? ' home__daydot--on' : ''}`}
              title={t(day.label)}
            >
              {day.done ? <Icon name="check" size={11} /> : null}
            </span>
          ))}
        </span>
        <Button className="home__continue" onClick={() => navigate('/prep')}>
          {t('Продолжить')}
        </Button>
      </div>
    </section>
  )
}

/** Мои эссе: черновики и то, что ушло куратору. */
function EssaysBlock() {
  const navigate = useNavigate()
  const essays = useMyEssays()
  const rows = (essays.data?.results ?? []).slice(0, 3)
  return (
    <section className="card card-pad card--accent card--brand">
      <header className="home__cardhead">
        <Tile icon="doc" tone="brand" size="lg" />
        <span className="home__cardtitle">
          <b>{t('Мои эссе')}</b>
          <span className="muted">{t('Черновики и то, что ушло куратору')}</span>
        </span>
        <button
          type="button"
          className="roundarrow home__plus"
          onClick={() => navigate('/essays')}
          aria-label={t('Новое эссе')}
        >
          <Icon name="plus" size={14} />
        </button>
      </header>
      {rows.length === 0 && (
        <p className="muted home__note">{t('Эссе ещё не заведено — начните с типа документа.')}</p>
      )}
      <Rows>
        {rows.map((essay) => {
          const last = essay.versions?.[0]
          return (
            <Row
              key={essay.id}
              icon="doc"
              tone="brand"
              title={essay.title}
              note={
                last
                  ? `${new Date(last.created_at).toLocaleDateString('ru')} · ${last.word_count} / ${essay.effective_word_limit} ${t('слов')}`
                  : (essay.doc_type_name ?? t('черновик без версий'))
              }
              right={<Badge variant={ESSAY_TONE[essay.status]}>{t(ESSAY_TITLE[essay.status])}</Badge>}
              onOpen={() => navigate('/essays')}
              openLabel={t('Открыть эссе')}
            />
          )
        })}
      </Rows>
    </section>
  )
}

/**
 * Готовность к подаче: общий процент и из чего он складывается.
 *
 * Домены без данных подписаны, а не спрятаны (C4 из аудита фазы 7):
 * пустая строка «данных пока нет» говорит ученику, что блок существует
 * и его кто-то ведёт, — исчезнувший блок читается как «этого у меня нет».
 * Внутренних ярлыков здесь нет и быть не может: их не отдаёт API
 * (инвариант №7), процент считается по значениям.
 */
function ReadinessBlock() {
  const { data } = useMyProfile()
  const readiness = data?.readiness
  if (!readiness) return null
  const rows = [
    ...readiness.parts.map((part) => ({ code: part.code, title: part.title, value: part.value })),
    ...readiness.skipped.map((part) => ({ code: part.code, title: part.title, value: null })),
  ]

  return (
    <section className="card card-pad card--accent card--brand home__ready">
      <header className="home__cardhead">
        <Tile icon="target" tone="brand" size="lg" />
        <span className="home__cardtitle">
          <b>{t('Готовность к подаче')}</b>
          <span className="muted">
            {readiness.weakest_title
              ? `${t('Больше всего сейчас даст')}: ${readiness.weakest_title}`
              : t('Из чего складывается ваш процент')}
          </span>
        </span>
        <b className="num home__readynum">{readiness.score}%</b>
      </header>

      <div className="home__readylist">
        {rows.map((row) => (
          <div key={row.code} className="home__readyrow">
            <span className="home__readyhead">
              <span>{row.title}</span>
              {row.value === null ? (
                <span className="muted">{t('данных пока нет')}</span>
              ) : (
                <b className="num">{Math.round(row.value)}%</b>
              )}
            </span>
            <div className="bar">
              <i
                style={{
                  width: `${row.value ?? 0}%`,
                  background: row.code === readiness.weakest ? 'var(--brand)' : 'var(--teal)',
                }}
              />
            </div>
          </div>
        ))}
        {rows.length === 0 && <p className="muted">{t('Данных пока нет — профиль ещё заполняется.')}</p>}
        {readiness.skipped.length > 0 && (
          <p className="muted home__readynote">
            {t('Блоки без данных в процент не входят — он считается по тем, что заполнены.')}
          </p>
        )}
      </div>
    </section>
  )
}

/** Мои вузы: план по каждой программе — статус, готовность, срок. */
function UniversitiesBlock() {
  const navigate = useNavigate()
  const plans = usePlans()
  const rows = (plans.data?.results ?? []).slice(0, 3)
  return (
    <section className="home__section">
      <header className="home__sectionhead">
        <b>{t('Мои вузы')}</b>
        <Button variant="outline" size="sm" onClick={() => navigate('/universities')}>
          {t('Смотреть все')}
        </Button>
      </header>
      <div className="home__unis">
        {rows.map((plan) => (
          <article key={plan.id} className="card card-pad home__uni">
            <header className="home__unihead">
              <Tile icon="cap" tone="indigo" size="lg" />
              <b>{plan.university_name}</b>
            </header>
            <div className="home__unifacts">
              <div>
                <div className="home__unival">{plan.counters.done > 0 ? t('В процессе') : t('Не начат')}</div>
                <div className="home__unilabel">{t('Статус')}</div>
              </div>
              <div>
                <div className="num home__unival">
                  {t('Готовность')} {plan.progress}%
                </div>
                <div className="home__unilabel">{t('План')}</div>
              </div>
              <div>
                <div className="home__unival">{plan.round_type || plan.level_title || '—'}</div>
                <div className="home__unilabel">{t('Раунд')}</div>
              </div>
              <div>
                <div
                  className={`num home__unival${
                    plan.days_left !== null && plan.days_left <= 30 ? ' home__unival--warn' : ''
                  }`}
                >
                  {plan.days_left === null ? '—' : `${plan.days_left} ${t('дн.')}`}
                </div>
                <div className="home__unilabel">{t('До дедлайна')}</div>
              </div>
            </div>
          </article>
        ))}
        {/* Пустое место в ряду — не дыра, а приглашение: одна строка
            и одна кнопка, как во всех пустых состояниях */}
        {rows.length < 3 && (
          <div className="empty home__uniempty">
            <span className="empty__icon" aria-hidden="true">
              <Icon name="cap" size={22} />
            </span>
            <p className="muted empty__what">{t('Добавьте вуз — план соберётся сам')}</p>
            <Button variant="outline" onClick={() => navigate('/catalog')}>
              {t('Открыть каталог')}
            </Button>
          </div>
        )}
      </div>
    </section>
  )
}

/** Материалы школы: три статьи из раздела «Ресурсы». */
function MaterialsBlock() {
  const navigate = useNavigate()
  const resources = useResources({})
  const rows = (resources.data?.results ?? []).slice(0, 3)
  if (rows.length === 0) return null
  return (
    <section className="home__section">
      <header className="home__sectionhead">
        <b>{t('Материалы школы')}</b>
        <Button variant="outline" size="sm" onClick={() => navigate('/resources')}>
          {t('Все материалы')}
        </Button>
      </header>
      <div className="home__unis">
        {rows.map((row) => (
          <button
            key={row.id}
            type="button"
            className="card card-pad home__material"
            onClick={() => navigate('/resources')}
          >
            <Badge variant="indigo">{row.category_name}</Badge>
            <b className="home__materialtitle">{row.title}</b>
            <span className="muted home__materialnote">{row.summary}</span>
            <span className="muted home__materialtime">
              {row.reading_minutes} {t('мин. чтения')}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}

export default function StudentHome() {
  const navigate = useNavigate()
  const journey = useJourney()
  const calendar = useCalendar()
  const [tipClosed, setTipClosed] = useState(false)

  if (journey.isLoading) return <Loading kind="cards" />
  if (journey.error) return <ErrorNote error={journey.error} />

  const steps = journey.data?.steps ?? []
  const complete = journey.data?.complete ?? false
  const open = steps.filter((step) => !step.done && !step.locked)
  const current = open[0] ?? null
  // подсказка появляется, когда открытых шагов больше одного: первый
  // и так стоит призывом в карточке рядом
  const skipped = open[1] ?? null

  return (
    <div className="home">
      <ScreenHead title={t('Главная')} subtitle={t('Ваши сроки, работа и то, что двинет дальше всего.')} />

      {skipped && !tipClosed && (
        <TipBar
          text={`${t('Не сделан шаг')}: ${t(skipped.title)}`}
          action={t('Открыть')}
          onAction={() => navigate(skipped.path)}
          onClose={() => setTipClosed(true)}
        />
      )}

      <div className="home__top">
        <CallToAction step={current} complete={complete} />
        <CalendarBlock events={calendar.data?.events ?? []} today={calendar.data?.today ?? ''} />
      </div>

      <div className="home__pair">
        <PrepBlock />
        <EssaysBlock />
      </div>

      <div className="home__pair">
        <TodayPanel />
        <ReadinessBlock />
      </div>

      <UniversitiesBlock />
      <MaterialsBlock />
    </div>
  )
}
