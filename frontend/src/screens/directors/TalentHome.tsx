/**
 * Главная директора талантов (макет THome, 24.10.2026): олимпиады месяца,
 * участники, освобождения недели и кто ждёт результата; ниже ближайшие
 * олимпиады и кто на этой неделе вне уроков.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useOlympiadEvents, useReleases } from '../../api/directors'
import PendingQueue from '../../components/PendingQueue'
import { Avatar, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { shiftDay, todayAlmaty } from '../../lib/dates'
import { LEVEL_TONE, olympiadDates } from './OlympiadEvents'
import { HomeColumns, MyStaffTasksCard, schoolWeekStart, todayLine, useGreeting } from './parts'
import { OlympiadDialog } from './talent'

export default function TalentHome() {
  const navigate = useNavigate()
  const greeting = useGreeting()
  const today = todayAlmaty()
  const from = schoolWeekStart(today)
  const olympiads = useOlympiadEvents()
  const releases = useReleases(from, shiftDay(from, 4))
  const [creating, setCreating] = useState(false)
  if (olympiads.isLoading || releases.isLoading) return <Loading kind="cards" />
  if (olympiads.error) return <ErrorNote error={olympiads.error} />

  const rows = olympiads.data?.rows ?? []
  const month = today.slice(0, 7)
  const thisMonth = rows.filter((row) => row.starts.slice(0, 7) === month)
  const next = rows.filter((row) => row.starts.slice(0, 7) > month)
  const soon = rows.filter((row) => row.ends >= today)
  const participants = rows
    .filter((row) => row.ends >= today)
    .reduce((sum, row) => sum + (row.participants ?? 0), 0)
  const waiting = rows.filter((row) => row.ends < today).reduce((sum, row) => sum + (row.pending ?? 0), 0)
  const away = (releases.data?.rows ?? []).flatMap((row) => row.students.map((student) => ({ student, row })))

  return (
    <div className="lay-screen">
      <ScreenHead
        title={greeting}
        subtitle={todayLine(t('олимпиады и освобождения от уроков'))}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate('/releases')}>
              {t('Освобождения')}
            </Button>
            <Button onClick={() => setCreating(true)}>{t('Добавить олимпиаду')}</Button>
          </>
        }
      />
      <div className="lay-4">
        <Kpi
          label={t('Олимпиад в этом месяце')}
          value={thisMonth.length}
          note={next.length ? t('дальше ещё {n}', { n: next.length }) : undefined}
          to="/olympiad-events"
        />
        <Kpi
          label={t('Участников')}
          value={participants}
          note={t('в предстоящих олимпиадах')}
          to="/olympiad-events"
        />
        <Kpi
          label={t('Освобождений на неделе')}
          value={away.length}
          note={
            releases.data ? olympiadDates({ starts: releases.data.from, ends: releases.data.to }) : undefined
          }
          to="/releases"
        />
        <Kpi
          label={t('Ждут результата')}
          value={waiting}
          chip={waiting ? { label: t('внести результат'), tone: 'warn' } : undefined}
          to="/olympiad-events"
        />
      </div>
      <MyStaffTasksCard />
      <PendingQueue fold hideEmpty />
      <HomeColumns
        main={[
          <DataCard
            className="card--beam"
            title={t('Ближайшие олимпиады')}
            count={soon.length || undefined}
            empty={soon.length === 0 && t('предстоящих олимпиад нет')}
            right={
              <Button variant="link" size="sm" onClick={() => navigate('/olympiad-events')}>
                {t('Все олимпиады')}
              </Button>
            }
          >
            <div className="dir__rows">
              {soon.slice(0, 5).map((row) => (
                <div key={row.id} className="dir__row">
                  <span className="dir__what">
                    <b>{row.title}</b>
                    <span className="t-note">
                      {[olympiadDates(row), row.place].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                  <Chip tone={LEVEL_TONE[row.level] ?? 'neutral'} size="sm">
                    {row.level_title}
                  </Chip>
                  <span className="dir__acts">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate(`/olympiad-events?open=${row.id}`)}
                    >
                      {t('Открыть')}
                    </Button>
                  </span>
                </div>
              ))}
            </div>
            {soon.length > 5 && (
              <Button variant="link" size="sm" onClick={() => navigate('/olympiad-events')}>
                {t('ещё {n}', { n: soon.length - 5 })}
              </Button>
            )}
          </DataCard>,
        ]}
        aside={[
          away.length > 0 && (
            <DataCard
              title={t('На этой неделе вне уроков')}
              count={away.length || undefined}
              right={
                <Button variant="link" size="sm" onClick={() => navigate('/releases')}>
                  {t('Неделя')}
                </Button>
              }
            >
              <div className="dir__rows">
                <ShowAll>
                  {away.map(({ student, row }) => (
                    <div key={`${row.id}-${student.id}`} className="dir__row">
                      <Avatar name={student.full_name} />
                      <span className="dir__what">
                        <b>{student.short_name}</b>
                        <span className="t-note">{`${student.group} · ${row.reason}`}</span>
                      </span>
                      <Chip tone="info" size="sm">
                        {olympiadDates(row)}
                      </Chip>
                      <span />
                    </div>
                  ))}
                </ShowAll>
              </div>
            </DataCard>
          ),
        ]}
      />
      {creating && olympiads.data && (
        <OlympiadDialog
          levels={olympiads.data.levels}
          onClose={() => setCreating(false)}
          onSaved={(row) => navigate(`/olympiad-events?open=${row.id}`)}
        />
      )}
    </div>
  )
}
