/**
 * Главная директора по поступлению (макет AHome, 24.10.2026): эссе, которые
 * ученики отправили на проверку, дедлайны вузов на 30 дней и то, что ждёт
 * решения Асем, — подтверждение прямо в строке (решение владельца, 24.10.2026:
 * раздела «Предложения» у директоров нет).
 */
import { useNavigate } from 'react-router'
import { useEssayReview } from '../../api/directors'
import { useDashboard, usePendingAdditions, useStudentQueue } from '../../api/hooks'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Avatar, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { formatDateTime, formatDayMonth } from '../../lib/format'
import { PendingAdditions } from '../dashboards/AdmissionDashboard'
import { daysLeft } from '../sections/Deadlines'
import type { AdmissionData } from '../sections/data'
import { HomeColumns, MyStaffTasksCard, todayLine, useGreeting } from './parts'

/** Окно дедлайнов главной — как у прежнего блока Асем (`URGENT_DAYS`). */
const WINDOW = 30

export default function AdmissionHome() {
  const navigate = useNavigate()
  const greeting = useGreeting()
  const essays = useEssayReview()
  const admission = useDashboard<AdmissionData>('admission')
  const queue = useStudentQueue()
  const additions = usePendingAdditions()
  if (essays.isLoading || admission.isLoading) return <Loading kind="cards" />
  if (essays.error) return <ErrorNote error={essays.error} />

  const waiting = (essays.data?.rows ?? []).filter((row) => !row.verdict)
  const soon = (admission.data?.deadlines ?? []).filter(
    (row) => daysLeft(row.deadline) >= 0 && daysLeft(row.deadline) <= WINDOW && row.applicants_count > 0,
  )
  const queued = queue.data?.results.length ?? 0

  return (
    <div className="lay-screen">
      <ScreenHead
        title={greeting}
        subtitle={todayLine(t('11 параллель, поступление'))}
        actions={<Button onClick={() => navigate('/essay-review')}>{t('Эссе учеников')}</Button>}
      />
      <div className="lay-4">
        <Kpi
          label={t('Эссе ждут проверки')}
          value={waiting.length}
          note={t('ученики отправили на проверку')}
          to="/essay-review"
        />
        <Kpi
          label={t('Дедлайны вузов за {n} дней', { n: WINDOW })}
          value={soon.length}
          note={
            soon.length ? t('до {date}', { date: formatDayMonth(soon[soon.length - 1].deadline) }) : undefined
          }
          to="/deadlines"
        />
        <Kpi label={t('Ждут вашего решения')} value={queued} note={t('внесли ученики')} />
        <Kpi
          label={t('Ученики добавили себе')}
          value={additions.data?.length ?? 0}
          note={t('вузы в списки')}
        />
      </div>
      <MyStaffTasksCard />
      {/* очередь — во всю ширину: «Подтвердить» и «Отклонить» стоят в одной строке */}
      <PendingQueue note={tk('Цели, специальности, страны и вузы в списках.')} fold hideEmpty />
      {/* ответы анкеты первого входа ждут подтверждения; пустая очередь не рисуется */}
      <OnboardingQueue />
      <HomeColumns
        main={[
          waiting.length > 0 && (
            <DataCard
              className="card--beam"
              title={t('Эссе учеников')}
              count={waiting.length || undefined}
              right={
                <Button variant="link" size="sm" onClick={() => navigate('/essay-review')}>
                  {t('Все эссе')}
                </Button>
              }
            >
              <div className="dir__rows">
                {waiting.slice(0, 5).map((row) => (
                  <div key={row.id} className="dir__row">
                    <Avatar name={row.student.full_name} />
                    <span className="dir__what">
                      <b>{row.student.short_name}</b>
                      <span className="t-note">
                        {[
                          row.kind,
                          tn(row.words, '{n} слово|{n} слова|{n} слов'),
                          row.submitted_at ? formatDateTime(row.submitted_at) : '',
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </span>
                    <Chip tone="accent" size="sm">
                      {t('ждёт проверки')}
                    </Chip>
                    <span className="dir__acts">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/essay-review?open=${row.id}`)}
                      >
                        {t('Открыть')}
                      </Button>
                    </span>
                  </div>
                ))}
              </div>
              {waiting.length > 5 && (
                <Button variant="link" size="sm" onClick={() => navigate('/essay-review')}>
                  {t('ещё {n}', { n: waiting.length - 5 })}
                </Button>
              )}
            </DataCard>
          ),
          (additions.data?.length ?? 0) > 0 && <PendingAdditions key="additions" />,
        ]}
        aside={[
          soon.length > 0 && (
            <DataCard
              title={t('Ближайшие дедлайны')}
              note={t('{n} дней', { n: WINDOW })}
              count={soon.length || undefined}
              right={
                <Button variant="link" size="sm" onClick={() => navigate('/deadlines')}>
                  {t('Все')}
                </Button>
              }
            >
              <div className="dir__rows">
                <ShowAll>
                  {soon.map((row) => (
                    <div key={row.id} className="dir__row">
                      <span className="dir__what">
                        <b>{row.university}</b>
                        <span className="t-note">{`${row.round_type} · ${tn(row.applicants_count, '{n} подаётся|{n} подаются|{n} подаются')}`}</span>
                      </span>
                      <Chip tone={row.tone} size="sm">
                        {formatDayMonth(row.deadline)}
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
    </div>
  )
}
