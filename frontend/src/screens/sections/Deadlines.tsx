/** Дедлайны — отдельный экран директора по поступлению (инвариант №4: дата живёт у вуза). */
import { useDashboard, usePlanAttention } from '../../api/hooks'
import { Button } from '../../components/ui/button'
import { useNavigate } from 'react-router-dom'
import Empty from '../../components/Empty'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { Chip, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { plural, t, tn } from '../../i18n'
import type { AdmissionData } from './data'

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
          'Дедлайн принадлежит вузу, а не ученику: он сдвигается один раз и у всех сразу.',
        )}
        action={t('Открыть справочник')}
        to="/directory"
      />
    )

  return (
    <div>
      <ScreenHead
        title={t('Дедлайны')}
      />

      <PlanAttention />

      {data.deadlines.length === 0 && (
        // пустой список — строка на всю ширину, а не карточка в клетке сетки
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

      {data.deadlines.length > 0 && (
        <div className="grid grid--cards">
          {data.deadlines.map((row) => {
            const left = daysLeft(row.deadline)
            return (
              <div key={row.id} className="card card-pad">
                <div className="row-between">
                  <div>
                    <b className="t-body">{row.university}</b>
                    <p className="muted t-note mt-1 mx-0 mb-0">
                      {row.country} · {row.round_type} · {row.program_name}
                    </p>
                  </div>
                  {/* цвет срока считает сервер по окнам из настроек школы */}
                  <Chip tone={row.tone} className="num">
                    {tn(left, '{n} дн')}
                  </Chip>
                </div>
                <div className="mt-3.5 pt-3 border-t border-(--line)">
                  <b className="num t-value">
                    {row.applicants_count}
                  </b>{' '}
                  <span className="muted t-note">
                    {plural(row.applicants_count, 'ученик подаётся|ученика подаются|учеников подаются')}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** Планы учеников: сколько создано и где прогресс нулевой при близком дедлайне. */
function PlanAttention() {
  const { data } = usePlanAttention()
  const navigate = useNavigate()
  if (!data || (data.total === 0 && data.stalled.length === 0)) return null
  return (
    <div className="card card-pad mb-4">
      <span className="eyebrow">
        {t('Планы поступления учеников')} · {data.total}
      </span>
      {data.stalled.length === 0 ? (
        <p className="muted t-note mt-1 mx-0 mb-0">
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
                  {tn(row.days_left, 'дедлайн через {n} день, прогресс нулевой|дедлайн через {n} дня, прогресс нулевой|дедлайн через {n} дней, прогресс нулевой')}
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
