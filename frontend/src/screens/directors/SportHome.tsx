/**
 * Главная директора спорта (макет SHome, 24.10.2026): мероприятия месяца,
 * новые заявки, ближайшее мероприятие с местами и зрителями, что дальше
 * в календаре и новые заявки с решением прямо в строке.
 */
import { useState } from 'react'
import { todayAlmaty } from '../../lib/dates'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import { useDecideApplication, useSportApplications, useSportEvents } from '../../api/directors'
import PendingQueue from '../../components/PendingQueue'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Avatar, ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDateTimeLong, formatDayMonth } from '../../lib/format'
import { MyStaffTasksCard, todayLine, useGreeting } from './parts'
import { EventDialog, seatsWords } from './SportEvents'

export default function SportHome() {
  const navigate = useNavigate()
  const greeting = useGreeting()
  const events = useSportEvents()
  const applications = useSportApplications()
  const decide = useDecideApplication()
  const [creating, setCreating] = useState(false)
  if (events.isLoading || applications.isLoading) return <Loading kind="cards" />
  if (events.error) return <ErrorNote error={events.error} />

  const rows = events.data?.rows ?? []
  const month = todayAlmaty().slice(0, 7)
  const thisMonth = rows.filter((row) => row.starts_at.slice(0, 7) === month)
  const competitions = thisMonth.filter((row) => row.kind === 'competition').length
  const upcoming = rows.filter((row) => !row.past)
  const next = upcoming[0]
  const fresh = applications.data?.rows ?? []

  return (
    <div className="lay-screen">
      <ScreenHead
        title={greeting}
        subtitle={todayLine(t('мероприятия и заявки учеников'))}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить мероприятие')}</Button>}
      />
      <div className="lay-4">
        <Kpi
          label={t('Мероприятий в этом месяце')}
          value={thisMonth.length}
          note={t('{c} соревнований · {e} мероприятий', { c: competitions, e: thisMonth.length - competitions })}
          to="/sport-events"
        />
        <Kpi label={t('Новых заявок')} value={fresh.length} note={t('ждут решения')} to="/sport-events" />
        <Kpi label={t('Участников на ближайшем')} value={next ? seatsWords(next) : null} note={next?.title} to={next ? `/sport-events?open=${next.id}` : '/sport-events'} />
        <Kpi label={t('Зрителей')} value={next?.spectators ? (next.watchers ?? 0) : null} note={t('записались смотреть')} />
      </div>
      <MyStaffTasksCard />
      <PendingQueue fold />
      <div className="lay-main lay-main--even">
        {next ? (
          <DataCard className="card--beam" title={t('Ближайшее мероприятие')} note={[next.title, next.kind_title, next.sport_title].filter(Boolean).join(' · ')}>
            <div className="dir__lines">
              <div className="dir__line">
                <span>{t('Дата')}</span>
                <b>{formatDateTimeLong(next.starts_at)}</b>
              </div>
              <div className="dir__line">
                <span>{t('Место')}</span>
                <b>{next.place}</b>
              </div>
              <div className="dir__line">
                <span>{t('Заявок')}</span>
                <b className="num">{t('участвовать {p} · смотреть {w}', { p: next.applications ?? 0, w: next.watchers ?? 0 })}</b>
              </div>
              <div className="dir__line">
                <span>{t('Мест для участников занято')}</span>
                <b className="num">{seatsWords(next)}</b>
              </div>
            </div>
            {next.seats !== null && <Bar percent={(next.accepted * 100) / Math.max(1, next.seats)} />}
            <div className="acad__actions">
              <Button variant="outline" onClick={() => navigate(`/sport-events?open=${next.id}`)}>
                {t('Открыть заявки')}
              </Button>
            </div>
          </DataCard>
        ) : (
          <DataCard title={t('Ближайшее мероприятие')} empty={t('мероприятий впереди нет')} emptyAction={<Button size="sm" variant="outline" onClick={() => setCreating(true)}>{t('Добавить')}</Button>} />
        )}
        <div className="lay-stack">
          <DataCard title={t('Дальше в календаре')} count={Math.max(0, upcoming.length - 1) || undefined} empty={upcoming.length <= 1 && t('дальше пока ничего нет')}>
            <div className="dir__rows">
              <ShowAll>
                {upcoming.slice(1).map((row) => (
                  <div key={row.id} className="dir__row">
                    <span className="dir__what">
                      <b>{row.title}</b>
                      <span className="t-note">{[row.kind_title, row.sport_title, row.place].filter(Boolean).join(' · ')}</span>
                    </span>
                    <Chip size="sm">{formatDayMonth(row.starts_at)}</Chip>
                    <span />
                  </div>
                ))}
              </ShowAll>
            </div>
          </DataCard>
          <DataCard
            title={t('Новые заявки')}
            count={fresh.length || undefined}
            empty={fresh.length === 0 && t('новых заявок нет')}
            right={
              <Button variant="link" size="sm" onClick={() => navigate('/sport-events')}>
                {t('Все')}
              </Button>
            }
          >
            <div className="dir__rows">
              <ShowAll>
                {fresh.map((row) => (
                  <div key={row.id} className="dir__row">
                    <Avatar name={row.student?.full_name ?? ''} />
                    <span className="dir__what">
                      <b>{row.student?.short_name}</b>
                      <span className="t-note">{[row.student?.group, row.event?.title, row.comment].filter(Boolean).join(' · ')}</span>
                    </span>
                    <span />
                    <span className="dir__acts">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: row.id, status: 'accepted' }, { onSuccess: () => toast.success(t('Заявка принята · ученик увидит статус')), onError: (reason) => toast.error(reason.message) })}
                      >
                        {t('Принять')}
                      </Button>
                      <RowMenu>
                        <RowMenuItem onClick={() => decide.mutate({ id: row.id, status: 'declined' }, { onSuccess: () => toast.success(t('Заявка отклонена · ученик увидит статус')) })}>
                          {t('Отклонить')}
                        </RowMenuItem>
                      </RowMenu>
                    </span>
                  </div>
                ))}
              </ShowAll>
            </div>
          </DataCard>
        </div>
      </div>
      {creating && <EventDialog onClose={() => setCreating(false)} onSaved={(row) => navigate(`/sport-events?open=${row.id}`)} />}
    </div>
  )
}
