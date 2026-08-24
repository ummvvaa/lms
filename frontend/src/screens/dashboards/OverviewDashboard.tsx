/** Директор школы: вся школа в нескольких цифрах. */
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
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
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty) return <EmptyDashboard title={t('Сводный вид')} />

  return (
    <div>
      <ScreenHead
        title={t('Сводный вид')}
        subtitle={t('Вся школа одним взглядом: средние, готовность и пять доменов.')}
      />

      <GettingStarted />

      <div className="grid grid--kpi">
        <Kpi
          value={`${data.average_readiness}%`}
          label={t('Средняя готовность')}
          note={`по ${data.total} ученикам`}
          color="var(--brand)"
        />
        <Kpi value={data.average_ielts ?? '—'} label={t('Средний IELTS')} note={t('цель 6.5+')} />
        <Kpi value={data.average_sat ?? '—'} label={t('Средний SAT')} note={t('цель 1300+')} />
        <Kpi value={data.ready_to_apply} label={t('Готовы к подаче')} color="var(--ok)" />
        <Kpi value={data.at_risk} label={t('В зоне риска')} note={t('нужен контроль')} color="var(--risk)" />
      </div>

      <div className="card card-pad">
        <span className="eyebrow">{t('Пять доменов')}</span>
        <div style={{ marginTop: 14 }}>
          {DOMAIN_TITLES.map(([code, title, owner]) => {
            const value = data.total ? Math.round(((data.domains[code] ?? 0) / data.total) * 100) : 0
            const color = value > 70 ? 'var(--teal)' : value > 45 ? 'var(--brand)' : 'var(--risk)'
            return (
              <div key={code} style={{ padding: '9px 0' }}>
                <div className="row-between" style={{ fontSize: 13, marginBottom: 6 }}>
                  <span style={{ fontWeight: 650 }}>
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
