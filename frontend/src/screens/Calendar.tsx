/**
 * Календарь ученика: месяц сеткой, справа «Ближайшее». В клетке месяца —
 * отметки событий точками; нажатие на день раскрывает его события полными
 * строками (образец `docs/ui/language/Calendar.html`, решение владельца
 * 27.09.2026). События живут у источников — целей, дедлайнов, стипендий,
 * соревнований, задач, СОР и СОЧ, сроков сдачи ДЗ — и по клику ведут туда.
 * На телефоне — лента ближайших, месяц крупными клетками по выбору.
 *
 * Раскладка по макету: вид и «Расписание уроков» в шапке справа; месяц — на
 * две трети с ключом цветов под сеткой, справа — выбранный день или
 * «Ближайшее» с бегущим светом.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useCalendar, type CalendarEvent } from '../api/hooks'
import CalendarCell, { type CalendarCellTone } from '../components/CalendarCell'
import { isoOf, shortDate, weekdays } from '../components/CalendarCard'
import Icon from '../layout/icons'
import { Row, Rows, Segmented, ShowAll } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t, tn } from '../i18n'
import { usePhone } from '../phone'
import { formatDayMonth, formatDayMonthShort, formatYearMonth } from '../lib/format'
import { useTrack } from '../usage/context'
import './dashboards/student.css'

const KIND_TONE: Record<string, CalendarCellTone> = {
  exam: 'accent',
  deadline: 'bad',
  competition: 'good',
  olympiad: 'good',
  scholarship: 'neutral',
  task: 'warn',
  assessment: 'info',
  // срок сдачи ДЗ в LMS: ведёт в задание, сданное из календаря уходит
  homework: 'warn',
}

export default function Calendar() {
  const trackFilter = useTrack('filter.change')
  const { data, isLoading, error } = useCalendar()
  const navigate = useNavigate()
  const phone = usePhone()
  const storageKey = 'calendar.mode.student'
  const [view, setViewState] = useState<'month' | 'list'>(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved === 'month' || saved === 'list') return saved
    } catch {
      /* память браузера недоступна — режим по умолчанию */
    }
    return phone ? 'list' : 'month'
  })
  const setView = (next: 'month' | 'list') => {
    setViewState(next)
    try {
      localStorage.setItem(storageKey, next)
    } catch {
      /* без памяти — режим живёт до перезагрузки */
    }
  }
  const [shift, setShift] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const today = data.today
  const base = new Date(today)
  const month = new Date(base.getFullYear(), base.getMonth() + shift, 1)
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const lead = (month.getDay() + 6) % 7
  const byDay = new Map<string, CalendarEvent[]>()
  for (const event of data.events) byDay.set(event.date, [...(byDay.get(event.date) ?? []), event])
  // СОР и СОЧ — не события, а подсвеченные дни: уроки живут в «Расписании»
  const workByDay = new Map<string, { title: string; short: string }[]>()
  for (const row of data.assessment_days ?? []) workByDay.set(row.date, [...(workByDay.get(row.date) ?? []), row])
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)]
  const upcoming = data.events.filter((event) => event.date >= today)
  const dayEvents = picked ? (byDay.get(picked) ?? []) : []
  const dayWork = picked ? (workByDay.get(picked) ?? []) : []

  const eventRow = (event: CalendarEvent, index: number) => (
    <Row
      key={`${event.date}-${index}`}
      lead={<span className="stu__when num">{shortDate(event.date, today)}</span>}
      title={event.title}
      note={event.kind_title}
      right={event.pending ? <Chip size="sm">{t('ждёт проверки')}</Chip> : undefined}
      to={event.link}
    />
  )

  // ключ цветов месяца: виды событий, что стоят в нём (СОР и СОЧ — подсветкой дня)
  const monthPrefix = isoOf(month.getFullYear(), month.getMonth(), 1).slice(0, 7)
  const legend = new Map<string, { title: string; tone: CalendarCellTone }>()
  if ((data.assessment_days ?? []).some((row) => row.date.startsWith(monthPrefix))) legend.set('assessment', { title: t('СОР или СОЧ'), tone: 'info' })
  for (const event of data.events)
    if (event.date.startsWith(monthPrefix) && !legend.has(event.kind)) legend.set(event.kind, { title: event.kind_title, tone: KIND_TONE[event.kind] ?? 'neutral' })

  const monthCard = (
    <DataCard
      className="lay-span2"
      title={formatYearMonth(month.getFullYear(), month.getMonth())}
      right={
        <span className="calx__nav">
          {shift !== 0 && (
            <Button variant="link" size="sm" onClick={() => { trackFilter(); setShift(0) }}>
              {t('К сегодня')}
            </Button>
          )}
          <Button variant="outline" size="icon-sm" aria-label={t('Прошлый месяц')} onClick={() => { trackFilter(); setShift(shift - 1) }}>
            <Icon name="chevronLeft" size={15} />
          </Button>
          <Button variant="outline" size="icon-sm" aria-label={t('Следующий месяц')} onClick={() => { trackFilter(); setShift(shift + 1) }}>
            <Icon name="chevronRight" size={15} />
          </Button>
        </span>
      }
    >
      <div className="stucal__grid" role="grid" aria-label={formatYearMonth(month.getFullYear(), month.getMonth())}>
        {weekdays().map((day) => (
          <span key={day} className="stucal__weekday t-caps">
            {day}
          </span>
        ))}
        {cells.map((day, index) => {
          if (day === null) return <CalendarCell key={`x${index}`} day={null} view={phone ? 'phone' : 'full'} />
          const iso = isoOf(month.getFullYear(), month.getMonth(), day)
          const events = (byDay.get(iso) ?? []).map((event) => ({ title: event.title, tone: KIND_TONE[event.kind] ?? 'neutral' }))
          return (
            <CalendarCell
              key={iso}
              day={day}
              view={phone ? 'phone' : 'full'}
              today={iso === today}
              picked={iso === picked}
              events={events}
              work={(workByDay.get(iso) ?? []).map((row) => row.short)}
              label={formatDayMonthShort(iso)}
              onPick={() => setPicked(iso === picked ? null : iso)}
            />
          )
        })}
      </div>
      {legend.size > 0 && (
        <div className="calx__legend">
          {[...legend.entries()].map(([kind, row]) => (
            <Chip key={kind} size="sm" tone={row.tone}>
              {row.title}
            </Chip>
          ))}
        </div>
      )}
    </DataCard>
  )

  const nearestCard = (
    <DataCard className={upcoming.length ? 'card--beam' : undefined} title={t('Ближайшее')} count={upcoming.length || undefined} empty={upcoming.length === 0 && t('впереди пока пусто')}>
      <Rows>
        <ShowAll>{upcoming.map(eventRow)}</ShowAll>
      </Rows>
    </DataCard>
  )

  // справа — выбранный день, без выбора — ближайшее; бегущий свет у неё одной,
  // свёрнутой пустой карточке свет не нужен
  const sideCard = picked ? (
    <DataCard className={dayEvents.length + dayWork.length ? 'card--beam' : undefined} title={formatDayMonth(picked)} count={dayEvents.length + dayWork.length || undefined} empty={dayEvents.length + dayWork.length === 0 && t('в этот день ничего не намечено')}>
      <Rows>
        {dayWork.map((row) => (
          <Row key={row.title} icon="pencil" tone="info" title={row.title} />
        ))}
        {dayEvents.map(eventRow)}
      </Rows>
    </DataCard>
  ) : (
    nearestCard
  )

  return (
    <div className="lay-screen calx">
      <ScreenHead
        title={t('Календарь')}
        subtitle={
          data.nearest
            ? `${data.nearest.title} — ${data.nearest.days_left === 0 ? t('сегодня') : tn(data.nearest.days_left, 'через {n} день|через {n} дня|через {n} дней')}`
            : undefined
        }
        actions={
          <>
            <Segmented
              value={view}
              onChange={setView}
              label={t('Вид календаря')}
              items={[
                { value: 'month', label: t('Месяц') },
                { value: 'list', label: t('Список') },
              ]}
            />
            <Button variant="outline" size="sm" onClick={() => navigate('/schedule')}>
              {t('Расписание уроков')}
            </Button>
          </>
        }
      />
      {view === 'month' ? (
        <div className="lay-3 calx__month">
          {monthCard}
          {sideCard}
        </div>
      ) : (
        nearestCard
      )}
    </div>
  )
}
