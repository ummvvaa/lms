/**
 * Кабинет Салтанат — школа (фаза 49).
 *
 * Первым идёт «Кому позвонить сегодня»: ученик, причина одной фразой,
 * чип срочности и телефон родителя прямо в строке — иначе звонок
 * откладывается до поисков контакта. Список собирается из пропусков,
 * моков, активности и дедлайнов, правила лежат справочником.
 *
 * Посещаемость и замечания она по-прежнему вносит сама: этого ученик
 * про себя не рассказывает.
 */
import { useNavigate } from 'react-router-dom'
import { useCabinet } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Row, Rows } from '../../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge, type BadgeVariant } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'

interface BehaviorCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  calls: {
    student_id: number
    student: string
    group: string
    urgency: string
    urgency_title: string
    reason: string
    contact: { name: string; phone: string } | null
  }[]
  groups: { id: number; code: string; students_count: number; risk: number }[]
  talks: { written: number; waiting: number }
}

const URGENCY: Record<string, BadgeVariant> = { now: 'risk', today: 'warn', week: 'mute' }

export default function BehaviorDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Школа')}
        hint={t('Здесь появится список тех, кому стоит позвонить')}
        what={t('Он собирается из пропусков, моков, активности и дедлайнов.')}
        detail={t('Правила и пороги вы ведёте сами в разделе «Правила обзвона».')}
        guide
      />
    )

  const cabinet = data as unknown as BehaviorCabinet

  return (
    <div>
      <ScreenHead
        title={t(cabinet.title)}
        subtitle={t(cabinet.owner)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/contacts')}>
              {t('Контакты родителей')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/call-rules')}>
              {t('Правила обзвона')}
            </Button>
            <Button size="sm" onClick={() => navigate('/table')}>
              {t('Внести посещаемость')}
            </Button>
          </>
        }
      />

      <GettingStarted />

      <CabinetColumns
        main={
          <DataCard
            title={t('Кому позвонить сегодня')}
            note={t('Собрано из пропусков, моков, активности и дедлайнов')}
            accent="risk"
            count={cabinet.calls.length}
          >
            {cabinet.calls.length === 0 && (
              <p className="muted rows__empty">
                {t('Сегодня звонить некому — ни одно правило не сработало.')}
              </p>
            )}
            {cabinet.calls.map((call) => (
              <div key={call.student_id} className="cabinet__row">
                <span className="cabinet__rowtext">
                  <b>
                    {call.student}
                    {call.group ? ` · ${call.group}` : ''}
                  </b>
                  <span className="muted">{t(call.reason)}</span>
                </span>
                <Badge variant={URGENCY[call.urgency] ?? 'mute'}>{t(call.urgency_title)}</Badge>
                {call.contact ? (
                  <Button variant="outline" size="sm" render={<a href={`tel:${call.contact.phone}`} />}>
                    {call.contact.name} · {call.contact.phone}
                  </Button>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => navigate('/contacts')}>
                    {t('Контакта нет')}
                  </Button>
                )}
              </div>
            ))}
          </DataCard>
        }
        aside={<CabinetStats stats={cabinet.stats} />}
      />

      <CabinetColumns
        main={
          <DataCard title={t('Учебные группы')} note={t('Цвет — сколько учеников в риске')} accent="brand">
            {cabinet.groups.length === 0 && <p className="muted rows__empty">{t('Групп пока нет')}</p>}
            <div className="cabinet__groups">
              {cabinet.groups.map((group) => (
                <button
                  key={group.id}
                  type="button"
                  className="cabinet__group"
                  onClick={() => navigate(`/table?group=${encodeURIComponent(group.code)}`)}
                >
                  <span className="cabinet__groupcode">
                    {group.code}
                    <span
                      className={`cabinet__grouprisk${group.risk === 0 ? ' cabinet__grouprisk--calm' : ''}`}
                    >
                      {group.risk} {t('в риске')}
                    </span>
                  </span>
                  <span className="cabinet__groupnote">
                    {group.students_count} {t('чел.')}
                  </span>
                </button>
              ))}
            </div>
          </DataCard>
        }
        aside={
          <>
            <OnboardingQueue />
            <PendingQueue note="Контакты родителей и то, что ученики рассказали о себе." />

            <DataCard title={t('Разговоры за неделю')} accent="teal">
              <Rows>
                <Row title={t('Записано')} note={`${cabinet.talks.written} ${t('разговоров')}`} />
                <Row
                  title={t('Ждут вашего ответа')}
                  note={`${cabinet.talks.waiting} ${t('вопросов от учеников')}`}
                  onOpen={() => navigate('/roadmap')}
                  openLabel={t('Открыть')}
                />
              </Rows>
            </DataCard>
          </>
        }
      />
    </div>
  )
}
