/** Кымбат: матрица шести корзин, кандидаты в TOP-30, падения моков. */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
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

const BUCKETS: [string, string, string][] = [
  ['ielts_low', 'IELTS < 6.0', 'var(--risk)'],
  ['ielts_mid', 'IELTS 6.0–7.4', 'var(--brand)'],
  ['ielts_high', 'IELTS 7.5+', 'var(--ok)'],
  ['sat_low', 'SAT < 1200', 'var(--risk)'],
  ['sat_mid', 'SAT 1200–1499', 'var(--brand)'],
  ['sat_high', 'SAT 1500+', 'var(--ok)'],
]

export default function ExamDashboard() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string | null>(null)
  const { data, isLoading, error } = useDashboard<Data>('exam')
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const total = Object.values(data.buckets).reduce((a, b) => a + b, 0) / 2 || 1

  return (
    <div>
      <ScreenHead emoji="🎯" title="Экзамены" subtitle="Экзаменационная матрица. Плитка кликается." />

      <div className="grid grid--kpi">
        {BUCKETS.map(([key, label, color]) => (
          <button
            key={key}
            className={`card card-pad kpi kpi--button${selected === key ? ' kpi--selected' : ''}`}
            style={selected === key ? { borderColor: color, borderWidth: 2 } : undefined}
            onClick={() => setSelected(selected === key ? null : key)}
          >
            <div className="num kpi__value" style={{ color }}>
              {data.buckets[key]}
            </div>
            <div className="kpi__label">{label}</div>
            <div style={{ marginTop: 12 }}>
              <Bar percent={(data.buckets[key] / total) * 100} color={color} />
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

      <h2 className="section">TOP-30 · кандидаты на SAT 1500+</h2>
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
