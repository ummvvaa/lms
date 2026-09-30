/**
 * Кабинет Нурлыбека — спорт (фаза 49).
 *
 * Первым — календарь стартов той же карточкой, что у ученика: сетка дней
 * с точками, справа список соревнований с числом участников. Не поданная
 * заявка помечена янтарным: это единственное, что здесь горит.
 */
import { useNavigate } from 'react-router-dom'
import { useCabinet } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import CalendarCard from '../../components/CalendarCard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'
import { formatDate } from '../../lib/format'

interface SportCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  starts: { title: string; date: string; students: number; applied: boolean }[]
  by_sport: { name: string; students: number }[]
}

/** Календарь стартов: та же карточка, что у ученика, только события общие.
 *  На телефоне у неё те же два режима — лента и месяц (фаза 51). */
function StartsCalendar({ starts }: { starts: SportCabinet['starts'] }) {
  const today = new Date()
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

  return (
    <CalendarCard
      events={starts.map((row) => ({
        date: row.date,
        title: row.title,
        note: (
          <>
            {formatDate(row.date)} · {row.students} {t('чел.')}
            {!row.applied && (
              <>
                {' · '}
                <b className="sport__notapplied">{t('заявка не подана')}</b>
              </>
            )}
          </>
        ),
        feedNote: (
          <>
            {row.students} {t('чел.')}
            {!row.applied && (
              <>
                {' · '}
                <b className="sport__notapplied">{t('заявка не подана')}</b>
              </>
            )}
          </>
        ),
      }))}
      today={todayIso}
      panelTitle="Календарь стартов"
      emptyText="Ближайших стартов нет."
      storageKey="calendar.mode.director_sport"
      withDateColumn={false}
    />
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

      {/* одна пара колонок: справа числа и сразу «По видам спорта», без пустоты
          под числами, которая оставалась, пока календарь был выше них */}
      <CabinetColumns
        main={
          <>
            <StartsCalendar starts={cabinet.starts} />
            <OnboardingQueue />
            <PendingQueue note="Выступления, разряды и виды спорта, которые внесли ученики." />
          </>
        }
        aside={
          <>
            <CabinetStats stats={cabinet.stats} />
            <DataCard title={t('По видам спорта')} note={t('Сколько учеников')}>
              {cabinet.by_sport.length === 0 && (
                <p className="muted rows__empty">{t('Вид спорта пока никто не указал')}</p>
              )}
              {cabinet.by_sport.map((row) => (
                <div key={row.name} className="cabinet__barrow">
                  <div className="cabinet__barhead">
                    <span>{row.name}</span>
                    <b className="num">{row.students}</b>
                  </div>
                  <Bar percent={(row.students / maxSport) * 100} color="var(--good)" />
                </div>
              ))}
              <Chip tone="neutral">{t('Значения меняет ученик, вы подтверждаете в очереди')}</Chip>
            </DataCard>
          </>
        }
      />
    </div>
  )
}
