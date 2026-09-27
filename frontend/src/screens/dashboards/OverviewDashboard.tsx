/** Директор школы: вся школа в нескольких цифрах. */
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import { StatRow } from '../../components/patterns'
import { Bar, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'

interface Data {
  total: number
  average_readiness: number
  average_ielts: number | null
  average_sat: number | null
  ready_to_apply: number
  at_risk: number
  domains: Record<string, number>
}

const DOMAIN_TITLES: [string, string, string][] = [
  ['behavior', 'Профиль и дисциплина', 'Салтанат'],
  ['admission', 'Поступление', 'Асем'],
  ['exam', 'Экзамены', 'Кымбат'],
  ['talent', 'Таланты', 'Арман'],
  ['sport', 'Спорт', 'Нурлыбек'],
]

export default function OverviewDashboard() {
  const { data, isLoading, error } = useDashboard<Data>('overview')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Сводный вид')}
        hint={t('Здесь появятся показатели по всей школе')}
        what={t('Вся школа одним экраном — когда появятся ученики.')}
        detail={t(
          'Средняя готовность, средние баллы и заполненность пяти доменов; числа считаются по всей школе.',
        )}
        guide
      />
    )

  return (
    <div>
      <ScreenHead
        title={t('Сводный вид')}
        subtitle={t('Вся школа одним взглядом: средние, готовность и пять доменов.')}
      />

      <GettingStarted />

      <StatRow>
        <Kpi
          value={`${data.average_readiness}%`}
          label={t('Средняя готовность')}
          note={`по ${data.total} ученикам`}
          tone="accent"
        />
        <Kpi value={data.average_ielts} label={t('Средний IELTS')} note={t('цель 6.5+')} tone="info" />
        <Kpi value={data.average_sat} label={t('Средний SAT')} note={t('цель 1300+')} />
        <Kpi value={data.ready_to_apply} label={t('Готовы к подаче')} tone="good" />
        <Kpi value={data.at_risk} label={t('В зоне риска')} note={t('нужен контроль')} tone="bad" />
      </StatRow>

      <div className="card card-pad">
        <span className="eyebrow">{t('Пять доменов')}</span>
        <div className="mt-3.5">
          {DOMAIN_TITLES.map(([code, title, owner]) => {
            const value = data.total ? Math.round(((data.domains[code] ?? 0) / data.total) * 100) : 0
            const color = value > 70 ? 'var(--info)' : value > 45 ? 'var(--accent)' : 'var(--bad)'
            return (
              <div key={code} className="py-2">
                <div className="row-between t-body mb-1.5">
                  <span className="font-semibold">
                    {title} <span className="muted">· {owner}</span>
                  </span>
                  <b className="num">{value}%</b>
                </div>
                <Bar percent={value} color={color} />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
