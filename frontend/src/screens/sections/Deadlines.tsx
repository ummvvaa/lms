/** Дедлайны — отдельный экран директора по поступлению (инвариант №4: дата живёт у вуза). */
import { useDashboard, usePlanAttention } from '../../api/hooks'
import { Button } from '../../components/ui/button'
import { useNavigate } from 'react-router-dom'
import Empty from '../../components/Empty'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { AdmissionData } from './data'
import { Badge } from '../../components/ui/badge'

/** Сколько дней осталось до даты раунда. */
export function daysLeft(date: string): number {
  return Math.round((new Date(date).getTime() - Date.now()) / 86_400_000)
}

export default function Deadlines() {
  const { data, isLoading, error } = useDashboard<AdmissionData>('admission')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Дедлайны')}
        hint={t('Здесь появятся ближайшие раунды подачи')}
        what={t('Заведите раунды в справочнике — дедлайны появятся здесь.')}
        detail={t(
          'Дедлайн принадлежит вузу, а не ученику: он сдвигается один раз и у всех сразу (инвариант №4).',
        )}
        action={t('Открыть справочник')}
        to="/directory"
      />
    )

  return (
    <div>
      <ScreenHead
        title={t('Дедлайны')}
        subtitle={t(
          'Ближайшие раунды подачи ваших учеников. Дедлайн принадлежит вузу: сдвиньте его в справочнике — он сдвинется у всех.',
        )}
      />

      <PlanAttention />

      <div className="grid grid--cards">
        {data.deadlines.map((row) => {
          const left = daysLeft(row.deadline)
          const tone = left < 30 ? 'risk' : left < 60 ? 'warn' : 'mute'
          return (
            <div key={row.id} className="card card-pad">
              <div className="row-between">
                <div>
                  <b style={{ fontSize: 14.5 }}>{row.university}</b>
                  <p className="muted" style={{ fontSize: 12.5, margin: '4px 0 0' }}>
                    {row.country} · {row.round_type} · {row.program_name}
                  </p>
                </div>
                <Badge variant={tone} className="num">
                  {left} дн
                </Badge>
              </div>
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
                <b className="num" style={{ fontSize: 19 }}>
                  {row.applicants_count}
                </b>{' '}
                <span className="muted" style={{ fontSize: 12.5 }}>
                  {t('учеников подаются')}
                </span>
              </div>
            </div>
          )
        })}
        {data.deadlines.length === 0 && (
          <Empty
            icon="clock"
            title={t('Ближайших дедлайнов нет')}
            what={t('Здесь будут раунды подачи на ближайшие 120 дней.')}
            hint={t(
              'Дедлайн живёт у вуза: заведите раунды в справочнике, и они появятся у всех, кто туда подаётся.',
            )}
            action={t('Открыть справочник')}
            to="/directory"
          />
        )}
      </div>
    </div>
  )
}

/** Планы учеников: сколько создано и где прогресс нулевой при близком дедлайне. */
function PlanAttention() {
  const { data } = usePlanAttention()
  const navigate = useNavigate()
  if (!data || (data.total === 0 && data.stalled.length === 0)) return null
  return (
    <div className="card card-pad" style={{ marginBottom: 16 }}>
      <span className="eyebrow">
        {t('Планы поступления учеников')} · {data.total}
      </span>
      {data.stalled.length === 0 ? (
        <p className="muted" style={{ fontSize: 12.5, margin: '4px 0 0' }}>
          {t('Застрявших планов нет: где создан план, там задачи двигаются.')}
        </p>
      ) : (
        <ul className="rows__list">
          {data.stalled.map((row) => (
            <li key={row.id} className="rows__item">
              <div className="rows__body">
                <span className="rows__label">
                  {row.student_name} · {row.university}
                </span>
                <span className="muted rows__note">
                  {t('дедлайн через')} {row.days_left} {t('дн., прогресс нулевой')}
                </span>
              </div>
              <Button variant="outline" size="sm" onClick={() => navigate(`/students/${row.student}`)}>
                {t('Открыть')}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
