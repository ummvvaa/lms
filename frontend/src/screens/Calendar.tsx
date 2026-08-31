/**
 * Календарь ученика (фаза 39): месяц и список ближайших.
 *
 * События живут у источников — целей, дедлайнов, стипендий, соревнований, задач —
 * и по клику ведут туда. Отправленное на проверку показывается
 * с пометкой: это календарь ученика и его слова.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCalendar, type CalendarEvent } from '../api/hooks'
import { ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { t } from '../i18n'

const KIND_TONE: Record<string, 'teal' | 'indigo' | 'ok' | 'warn'> = {
  exam: 'teal',
  deadline: 'indigo',
  competition: 'ok',
  olympiad: 'warn',
  // стипендия — дедлайн подачи из справочника (фаза 44)
  scholarship: 'indigo',
  task: 'warn',
}

const MONTHS = [
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

function MonthGrid({ events, month, today }: { events: CalendarEvent[]; month: Date; today: string }) {
  const navigate = useNavigate()
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  // неделя начинается с понедельника
  const lead = (first.getDay() + 6) % 7
  const byDay = new Map<string, CalendarEvent[]>()
  for (const event of events) {
    byDay.set(event.date, [...(byDay.get(event.date) ?? []), event])
  }

  const cells: (number | null)[] = [
    ...Array(lead).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]

  return (
    <div className="cal__grid" role="grid" aria-label={`${MONTHS[month.getMonth()]} ${month.getFullYear()}`}>
      {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((day) => (
        <div key={day} className="muted cal__weekday">
          {t(day)}
        </div>
      ))}
      {cells.map((day, index) => {
        if (day === null) return <div key={`x${index}`} className="cal__cell cal__cell--blank" />
        const iso = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
        const dayEvents = byDay.get(iso) ?? []
        return (
          <div key={iso} className={`cal__cell${iso === today ? ' cal__cell--today' : ''}`}>
            <span className="num cal__day">{day}</span>
            {dayEvents.slice(0, 3).map((event, i) => (
              <button key={i} className="cal__event" onClick={() => navigate(event.link)} title={event.title}>
                {event.title}
              </button>
            ))}
            {dayEvents.length > 3 && (
              <span className="muted cal__more">
                …{t('и ещё')} {dayEvents.length - 3}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function Calendar() {
  const { data, isLoading, error } = useCalendar()
  const navigate = useNavigate()
  const [view, setView] = useState<'month' | 'list'>('month')
  const [shift, setShift] = useState(0)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const base = new Date(data.today)
  const month = new Date(base.getFullYear(), base.getMonth() + shift, 1)
  const upcoming = data.events.filter((event) => event.date >= data.today)

  return (
    <div>
      <ScreenHead
        title={t('Календарь')}
        subtitle={t('Экзамены, дедлайны, соревнования и задачи — по клику открывается источник.')}
      />

      {data.nearest && (
        <div className="card card-pad card--accent card--teal cal__nearest">
          <span className="eyebrow">{t('Ближайшее событие')}</span>
          <div className="cal__nearestrow">
            <div>
              <div className="t-card cal__nearesttitle">
                {data.nearest.title}
                {data.nearest.pending && <Badge variant="mute">{t('ждёт проверки')}</Badge>}
              </div>
              <p className="muted cal__nearestnote">{new Date(data.nearest.date).toLocaleDateString('ru')}</p>
            </div>
            <div className="num t-figure">
              {data.nearest.days_left === 0 ? t('сегодня') : `${data.nearest.days_left} ${t('дн.')}`}
            </div>
          </div>
        </div>
      )}

      <ScreenTabs
        value={view}
        onChange={setView}
        items={[
          { value: 'month', label: t('Месяц') },
          { value: 'list', label: t('Ближайшие') },
        ]}
      />

      {view === 'month' && (
        <div className="card card-pad">
          <div className="row-between cal__monthhead">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShift(shift - 1)}
              aria-label={t('Прошлый месяц')}
            >
              ←
            </Button>
            <b>
              {t(MONTHS[month.getMonth()])} {month.getFullYear()}
            </b>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShift(shift + 1)}
              aria-label={t('Следующий месяц')}
            >
              →
            </Button>
          </div>
          <MonthGrid events={data.events} month={month} today={data.today} />
        </div>
      )}

      {view === 'list' && (
        <div className="card card-pad">
          {upcoming.length === 0 && (
            <p className="muted">{t('Впереди пока пусто — поставьте цель по экзамену или выберите вузы.')}</p>
          )}
          <ul className="rows__list">
            {upcoming.slice(0, 30).map((event, index) => (
              <li key={index} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">
                    {event.title}
                    {event.pending && <Badge variant="mute">{t('ждёт проверки')}</Badge>}{' '}
                    <Badge variant={KIND_TONE[event.kind] ?? 'mute'}>
                      {new Date(event.date).toLocaleDateString('ru')}
                    </Badge>
                  </span>
                </div>
                <Button variant="outline" size="sm" onClick={() => navigate(event.link)}>
                  {t('Открыть')}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
