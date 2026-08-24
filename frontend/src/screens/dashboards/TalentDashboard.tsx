/** Арман: распределение портфолио, шесть треков, обратный отсчёт до 1 ноября. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import { Donut, ErrorNote, Kpi, ListPanel, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'

interface Row {
  student_id: number
  student__last_name: string
  student__first_name: string
  portfolio_status?: string
}

interface Data {
  portfolio: Record<string, number>
  tracks: Record<string, number>
  days_to_november: number
  no_track: Row[]
  weak_portfolio: Row[]
  categories: Record<string, number>
}

const TRACK_TITLES: Record<string, string> = {
  olympiad: 'Олимпиады',
  research: 'Исследования',
  startup: 'Стартап',
  leadership: 'Лидерство',
  volunteering: 'Волонтёрство',
  competition: 'Конкурсы',
  unset: 'Трек не выбран',
}

export default function TalentDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<Data>('talent')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty) return <EmptyDashboard title={t('Таланты')} />

  const strong = data.portfolio.strong ?? 0
  const medium = data.portfolio.medium ?? 0
  const weak = data.portfolio.weak ?? 0

  return (
    <div>
      <ScreenHead title={t('Таланты')} subtitle={t('Чем каждый ученик может усилить свою заявку.')} />

      <GettingStarted />

      <div className="grid grid--kpi">
        <Kpi
          value={data.days_to_november}
          label={t('дней до 1 ноября')}
          note={t('дедлайн закрытия пробелов')}
          color="var(--brand)"
        />
        <Kpi value={strong} label={t('Сильное портфолио')} color="var(--ok)" />
        <Kpi value={medium} label={t('Среднее портфолио')} color="var(--warn)" />
        <Kpi value={weak} label={t('Слабое портфолио')} note={t('нужен план усиления')} color="var(--risk)" />
      </div>

      <div className="split">
        <div className="card card-pad">
          <span className="eyebrow">{t('Распределение')}</span>
          <div className="row-between" style={{ marginTop: 16 }}>
            <Donut
              segments={[
                { value: strong, color: 'var(--ok)' },
                { value: medium, color: 'var(--warn)' },
                { value: weak, color: 'var(--risk)' },
              ]}
            />
            <div className="legend">
              {[
                ['Сильное', 'var(--ok)', strong],
                ['Среднее', 'var(--warn)', medium],
                ['Слабое', 'var(--risk)', weak],
              ].map(([label, color, value]) => (
                <div key={String(label)} className="legend__row">
                  <span className="legend__dot" style={{ background: String(color) }} />
                  <span className="muted">{label}</span>
                  <b className="num legend__value">{value}</b>
                </div>
              ))}
            </div>
          </div>
          <div style={{ marginTop: 18, paddingTop: 18, borderTop: '1px solid var(--line)' }}>
            <div className="muted" style={{ fontSize: 12, fontWeight: 700, marginBottom: 10 }}>
              {t('По трекам')}
            </div>
            {Object.entries(TRACK_TITLES)
              .filter(([key]) => key !== 'unset')
              .map(([key, title]) => (
                <div key={key} className="row-between" style={{ padding: '4px 0', fontSize: 12.5 }}>
                  <span>{title}</span>
                  <b className="num">{data.tracks[key] ?? 0}</b>
                </div>
              ))}
          </div>
        </div>

        <ListPanel
          title={t('Слабое портфолио — приоритет')}
          rows={data.weak_portfolio}
          onOpen={(id) => navigate(`/students/${id}`)}
        />
      </div>

      <h2 className="section" id="tracks">
        {t('Трек не выбран — нужно решение')}
      </h2>
      <ListPanel
        title={t('Без основного трека')}
        rows={data.no_track}
        limit={15}
        onOpen={(id) => navigate(`/students/${id}`)}
      />
    </div>
  )
}
