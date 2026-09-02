/**
 * Кабинет Нурлыбека — спорт (фаза 49).
 *
 * Первым — календарь стартов той же карточкой, что у ученика: сетка дней
 * с точками, справа список соревнований с числом участников. Не поданная
 * заявка помечена янтарным: это единственное, что здесь горит.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCabinet } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Row, Rows } from '../../components/patterns'
import { Bar, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import Icon from '../../layout/icons'
import { t } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'
import './home.css'

interface SportCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  starts: { title: string; date: string; students: number; applied: boolean }[]
  by_sport: { name: string; students: number }[]
}

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

/** Календарь стартов: та же карточка, что у ученика, только события общие. */
function StartsCalendar({ starts }: { starts: SportCabinet['starts'] }) {
  const [shift, setShift] = useState(0)
  const today = new Date()
  const month = new Date(today.getFullYear(), today.getMonth() + shift, 1)
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const lead = (month.getDay() + 6) % 7
  const marked = new Set(starts.map((row) => row.date))
  const cells: (number | null)[] = [
    ...Array<null>(lead).fill(null),
    ...Array.from({ length: daysInMonth }, (_, index) => index + 1),
  ]
  const iso = (day: number) =>
    `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

  return (
    <section className="hero hero--indigo home__cal home__cal--wide">
      <div className="home__calleft">
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
          {cells.map((day, index) =>
            day === null ? (
              <span key={`x${index}`} />
            ) : (
              <span
                key={iso(day)}
                className={`num home__calday${iso(day) === todayIso ? ' home__calday--today' : ''}${
                  marked.has(iso(day)) ? ' home__calday--marked' : ''
                }`}
              >
                {day}
              </span>
            ),
          )}
        </div>
      </div>

      <div className="home__calpanel">
        <span className="home__panelhead">{t('Календарь стартов')}</span>
        {starts.length === 0 && <p className="muted home__calempty">{t('Ближайших стартов нет.')}</p>}
        <Rows>
          {starts.map((row) => (
            <Row
              key={`${row.title}-${row.date}`}
              title={row.title}
              note={
                <>
                  {new Date(row.date).toLocaleDateString('ru')} · {row.students} {t('чел.')}
                  {!row.applied && (
                    <>
                      {' · '}
                      <b className="sport__notapplied">{t('заявка не подана')}</b>
                    </>
                  )}
                </>
              }
            />
          ))}
        </Rows>
      </div>
    </section>
  )
}

export default function SportDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Спорт')}
        hint={t('Здесь появится календарь стартов')}
        what={t('Соревнования вносите вы, выступления отмечают ученики.')}
        detail={t('Начните со справочника видов спорта.')}
        guide
      />
    )

  const cabinet = data as unknown as SportCabinet
  const maxSport = Math.max(1, ...cabinet.by_sport.map((row) => row.students))

  return (
    <div>
      <ScreenHead
        title={t(cabinet.title)}
        subtitle={t(cabinet.owner)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/sport-types')}>
              {t('Виды спорта')}
            </Button>
            <Button size="sm" onClick={() => navigate('/competitions')}>
              {t('Добавить соревнование')}
            </Button>
          </>
        }
      />

      <GettingStarted />

      <CabinetColumns
        main={<StartsCalendar starts={cabinet.starts} />}
        aside={<CabinetStats stats={cabinet.stats} />}
      />

      <CabinetColumns
        main={
          <>
            <OnboardingQueue />
            <PendingQueue note="Выступления, разряды и виды спорта, которые внесли ученики." />
          </>
        }
        aside={
          <DataCard title={t('По видам спорта')} note={t('Сколько учеников')} accent="ok">
            {cabinet.by_sport.length === 0 && (
              <p className="muted rows__empty">{t('Вид спорта пока никто не указал')}</p>
            )}
            {cabinet.by_sport.map((row) => (
              <div key={row.name} className="cabinet__barrow">
                <div className="cabinet__barhead">
                  <span>{row.name}</span>
                  <b className="num">{row.students}</b>
                </div>
                <Bar percent={(row.students / maxSport) * 100} color="var(--ok)" />
              </div>
            ))}
            <Badge variant="mute">{t('Значения меняет ученик, вы подтверждаете в очереди')}</Badge>
          </DataCard>
        }
      />
    </div>
  )
}
