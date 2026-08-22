/** Кымбат: матрица шести корзин, кандидаты в TOP-30, падения моков. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import OnboardingQueue from '../../components/OnboardingQueue'
import { Bar, ErrorNote, ListPanel, Loading, ScreenHead } from '../../components/ui'

interface Row {
  student_id: number
  student__last_name: string
  student__first_name: string
  ielts_current?: string
  ielts_target?: string
  sat_current?: number
  sat_target?: number
}

interface Drop {
  student_id: number
  student__last_name: string
  student__first_name: string
  exam_type: string
  latest: number
  previous: number
  delta: number
}

interface Data {
  buckets: Record<string, number>
  top_ielts: Row[]
  top_sat: Row[]
  mock_drops: Drop[]
  averages: { ielts: string | null; sat: number | null }
}

interface Bucket {
  key: string
  label: string
  color: string
  /** фильтр таблицы: плитка должна показывать этих учеников, а не просто подсвечиваться */
  filter: Record<string, string>
}

const BUCKETS: Bucket[] = [
  { key: 'ielts_low', label: 'IELTS < 6.0', color: 'var(--risk)', filter: { ielts_max: '6.0' } },
  {
    key: 'ielts_mid',
    label: 'IELTS 6.0–7.4',
    color: 'var(--brand)',
    filter: { ielts_min: '6.0', ielts_max: '7.5' },
  },
  { key: 'ielts_high', label: 'IELTS 7.5+', color: 'var(--ok)', filter: { ielts_min: '7.5' } },
  { key: 'sat_low', label: 'SAT < 1200', color: 'var(--risk)', filter: { sat_max: '1200' } },
  {
    key: 'sat_mid',
    label: 'SAT 1200–1499',
    color: 'var(--brand)',
    filter: { sat_min: '1200', sat_max: '1500' },
  },
  { key: 'sat_high', label: 'SAT 1500+', color: 'var(--ok)', filter: { sat_min: '1500' } },
]

export default function ExamDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<Data>('exam')
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const total = Object.values(data.buckets).reduce((a, b) => a + b, 0) / 2 || 1

  return (
    <div>
      <ScreenHead
        emoji="🎯"
        title="Экзамены"
        subtitle="Экзаменационная матрица. Плитка открывает этих учеников в таблице."
      />

      <OnboardingQueue />

      <div className="grid grid--kpi">
        {BUCKETS.map((bucket) => (
          <button
            key={bucket.key}
            className="card card-pad kpi kpi--button"
            onClick={() => navigate(`/table?${new URLSearchParams(bucket.filter).toString()}`)}
          >
            <div className="num kpi__value" style={{ color: bucket.color }}>
              {data.buckets[bucket.key]}
            </div>
            <div className="kpi__label">{bucket.label}</div>
            <div style={{ marginTop: 12 }}>
              <Bar percent={(data.buckets[bucket.key] / total) * 100} color={bucket.color} />
            </div>
          </button>
        ))}
      </div>

      <div className="grid grid--two">
        <ListPanel
          title="TOP-30 · кандидаты на IELTS 7.5+"
          rows={data.top_ielts}
          limit={30}
          onOpen={(id) => navigate(`/students/${id}`)}
          right={(row) => (
            <span className="num" style={{ textAlign: 'right', fontSize: 13 }}>
              <b>{row.ielts_current}</b>
              <br />
              <span className="muted" style={{ fontSize: 11 }}>
                цель {row.ielts_target ?? '—'}
              </span>
            </span>
          )}
        />
        <ListPanel
          title="Мок упал — нужна интервенция"
          rows={data.mock_drops}
          limit={20}
          onOpen={(id) => navigate(`/students/${id}`)}
          right={(row) => (
            <span className="chip chip-risk num">
              {row.exam_type} {row.delta}
            </span>
          )}
        />
      </div>

      <h2 className="section" id="top30">
        TOP-30 · кандидаты на SAT 1500+
      </h2>
      <ListPanel
        title="По текущему SAT"
        rows={data.top_sat}
        limit={30}
        onOpen={(id) => navigate(`/students/${id}`)}
        right={(row) => (
          <span className="num" style={{ textAlign: 'right', fontSize: 13 }}>
            <b>{row.sat_current}</b>
            <br />
            <span className="muted" style={{ fontSize: 11 }}>
              цель {row.sat_target ?? '—'}
            </span>
          </span>
        )}
      />
    </div>
  )
}
