/**
 * Календарь ученика: месяц сеткой с событиями в клетках, справа «Ближайшее»
 * и «Откуда события». События живут у источников — целей, дедлайнов,
 * стипендий, соревнований, задач, СОР и СОЧ — и по клику ведут туда.
 * На телефоне — лента ближайших, месяц крупными клетками по выбору.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCalendar, type CalendarEvent } from '../api/hooks'
import CalendarCell, { type CalendarCellTone } from '../components/CalendarCell'
import { EVENT_KIND_TITLE, isoOf, MONTH_NAMES, MONTHS, shortDate, WEEKDAYS } from '../components/CalendarCard'
import Icon from '../layout/icons'
import { Row, Rows, Segmented, ShowAll } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { usePhone } from '../phone'
import './dashboards/student.css'

const KIND_TONE: Record<string, CalendarCellTone> = {
  exam: 'accent',
  deadline: 'bad',
  competition: 'good',
  olympiad: 'good',
  scholarship: 'neutral',
  task: 'warn',
  assessment: 'info',
}

const LEGEND: { kind: string; title: string }[] = [
  { kind: 'exam', title: 'Экзамены и регистрация' },
  { kind: 'assessment', title: 'СОР и СОЧ по расписанию' },
  { kind: 'deadline', title: 'Дедлайны вузов' },
  { kind: 'task', title: 'Задачи плана и куратора' },
  { kind: 'scholarship', title: 'Стипендии' },
  { kind: 'competition', title: 'Соревнования и олимпиады' },
]

export default function Calendar() {
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
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)]
  const upcoming = data.events.filter((event) => event.date >= today)
  const dayEvents = picked ? (byDay.get(picked) ?? []) : []

  const eventRow = (event: CalendarEvent, index: number) => (
    <Row
      key={`${event.date}-${index}`}
      lead={<span className="stu__when num">{shortDate(event.date, today)}</span>}
      title={event.title}
      note={t(EVENT_KIND_TITLE[event.kind] ?? 'Событие')}
      right={event.pending ? <Chip size="sm">{t('ждёт проверки')}</Chip> : undefined}
      to={event.link}
    />
  )

  const monthCard = (
    <DataCard title={t('Месяц')}>
      <div className="stucal__head">
        <Button variant="outline" size="icon-sm" aria-label={t('Прошлый месяц')} onClick={() => setShift(shift - 1)}>
          <Icon name="chevronLeft" size={15} />
        </Button>
        <span className="stucal__title">
          {t(MONTH_NAMES[month.getMonth()])} {month.getFullYear()}
        </span>
        <Button variant="outline" size="icon-sm" aria-label={t('Следующий месяц')} onClick={() => setShift(shift + 1)}>
          <Icon name="chevronRight" size={15} />
        </Button>
      </div>
      <div className="stucal__grid" role="grid" aria-label={`${t(MONTH_NAMES[month.getMonth()])} ${month.getFullYear()}`}>
        {WEEKDAYS.map((day) => (
          <span key={day} className="stucal__weekday t-caps">
            {t(day)}
          </span>
        ))}
        {cells.map((day, index) => {
          if (day === null) return <CalendarCell key={`x${index}`} day={null} view={phone ? 'phone' : 'full'} />
          const iso = isoOf(month.getFullYear(), month.getMonth(), day)
          const events = (byDay.get(iso) ?? []).map((event) => ({ title: event.title, tone: KIND_TONE[event.kind] ?? 'neutral' }))
          return <CalendarCell key={iso} day={day} view={phone ? 'phone' : 'full'} today={iso === today} picked={iso === picked} events={events} onPick={() => setPicked(iso === picked ? null : iso)} />
        })}
      </div>
      {picked && (
        <DataCard title={`${Number(picked.slice(8))} ${t(MONTHS[Number(picked.slice(5, 7)) - 1])}`} empty={dayEvents.length === 0 && t('в этот день ничего не намечено')}>
          <Rows>{dayEvents.map(eventRow)}</Rows>
        </DataCard>
      )}
    </DataCard>
  )

  const nearestCard = (
    <DataCard title={t('Ближайшее')} count={upcoming.length || undefined} empty={upcoming.length === 0 && t('впереди пока пусто — поставьте цель по экзамену или выберите вузы')}>
      <Rows>
        <ShowAll>{upcoming.map(eventRow)}</ShowAll>
      </Rows>
    </DataCard>
  )

  const legendCard = (
    <DataCard title={t('Откуда события')}>
      <div className="stucal__legend">
        {LEGEND.map((row) => (
          <span key={row.kind} className="stucal__key">
            <i className={`stucal__dot stucal__dot--${KIND_TONE[row.kind]}`} aria-hidden="true" />
            {t(row.title)}
          </span>
        ))}
        <span className="t-note">{t('Напоминания приходят за 14 и за 3 дня')}</span>
      </div>
    </DataCard>
  )

  return (
    <div>
      <ScreenHead
        title={t('Календарь')}
        subtitle={
          data.nearest
            ? `${data.nearest.title} — ${data.nearest.days_left === 0 ? t('сегодня') : `${t('через')} ${data.nearest.days_left} ${t('дн.')}`}`
            : t('Экзамены, дедлайны, СОР и СОЧ, задачи — по клику открывается источник')
        }
      />
      <div className="acad__toolbar">
        <Segmented
          value={view}
          onChange={setView}
          label={t('Вид календаря')}
          items={[
            { value: 'month', label: t('Месяц') },
            { value: 'list', label: t('Список') },
          ]}
        />
        {view === 'month' && shift !== 0 && (
          <Button variant="link" size="sm" onClick={() => setShift(0)}>
            {t('К сегодня')}
          </Button>
        )}
      </div>
      {phone ? (
        <div className="acad__stack">
          {view === 'month' ? monthCard : nearestCard}
          {legendCard}
        </div>
      ) : (
        <div className="acad__cols">
          <div className="acad__stack">{view === 'month' ? monthCard : nearestCard}</div>
          <div className="acad__stack">
            {view === 'month' && nearestCard}
            {legendCard}
            <Button variant="outline" size="sm" onClick={() => navigate('/schedule')}>
              {t('Расписание уроков')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
