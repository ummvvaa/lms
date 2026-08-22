/** Асем: счётчик слотов, распределение A/B/C, календарь дедлайнов, без Common App. */
import { useNavigate } from 'react-router-dom'
import { useDashboard, usePendingAdditions, useReviewAddition } from '../../api/hooks'
import { Bar, Donut, ErrorNote, Kpi, ListPanel, Loading, ScreenHead } from '../../components/ui'

interface Row {
  student_id: number
  student__last_name: string
  student__first_name: string
  status?: string
}

interface Deadline {
  id: number
  deadline: string
  round_type: string
  applicants_count: number
  university: string
  country: string
  program_name: string
}

interface Data {
  total: number
  slots: number
  slots_target: number
  statuses: Record<string, number>
  with_three_universities: number
  deadlines: Deadline[]
  popular: { name: string; n: number }[]
  no_common_app: Row[]
  no_application_account: Row[]
}

function daysLeft(date: string): number {
  return Math.round((new Date(date).getTime() - Date.now()) / 86_400_000)
}

/** Что ученики добавили себе сами — отдельным списком, до подтверждения. */
function PendingAdditions() {
  const pending = usePendingAdditions()
  const review = useReviewAddition()
  const rows = pending.data ?? []
  if (rows.length === 0) return null

  return (
    <div className="card card-pad" style={{ marginBottom: 16, borderColor: 'var(--brand)' }}>
      <span className="eyebrow">⚠ Ученики добавили себе</span>
      <p className="muted" style={{ fontSize: 12.5, margin: '6px 0 0' }}>
        Пока вы не подтвердите, запись остаётся пометкой ученика, а не решением школы.
      </p>
      {rows.map((row) => (
        <div key={row.id} className="row-between" style={{ padding: '10px 0', gap: 12 }}>
          <span>
            <b>{row.student_name}</b> → {row.university_name} · {row.program_name}
            <span className="muted"> ({row.tier})</span>
          </span>
          <span style={{ display: 'flex', gap: 6 }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => review.mutate({ id: row.id, decision: 'confirm' })}
              disabled={review.isPending}
            >
              Подтвердить
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => review.mutate({ id: row.id, decision: 'decline' })}
              disabled={review.isPending}
            >
              Снять
            </button>
          </span>
        </div>
      ))}
    </div>
  )
}

export default function AdmissionDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<Data>('admission')
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const a = data.statuses.A ?? 0
  const b = data.statuses.B ?? 0
  const c = data.statuses.C ?? 0
  const top = data.popular[0]?.n ?? 1

  return (
    <div>
      <ScreenHead
        emoji="🎓"
        title="Поступление"
        subtitle={`Цель: 3 университета на каждого ученика — минимум ${data.slots_target} слотов.`}
      />

      <PendingAdditions />

      <div className="grid grid--kpi">
        <Kpi
          value={data.slots}
          label="University slots"
          note={`цель ${data.slots_target}`}
          color="var(--brand)"
        />
        <Kpi value={a} label="Готовы к подаче" color="var(--ok)" />
        <Kpi value={b} label="Требуют подготовки" color="var(--warn)" />
        <Kpi value={c} label="Критические" color="var(--risk)" />
      </div>

      <div className="split">
        <div className="card card-pad">
          <span className="eyebrow">Admission readiness</span>
          <div className="row-between" style={{ marginTop: 16 }}>
            <Donut
              segments={[
                { value: a, color: 'var(--ok)' },
                { value: b, color: 'var(--warn)' },
                { value: c, color: 'var(--risk)' },
              ]}
            />
            <div className="legend">
              {[
                ['A', 'var(--ok)', a],
                ['B', 'var(--warn)', b],
                ['C', 'var(--risk)', c],
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
            <div className="row-between" style={{ fontSize: 12.5, marginBottom: 6 }}>
              <span className="muted">Есть 3+ вуза</span>
              <b className="num">
                {data.with_three_universities} из {data.total}
              </b>
            </div>
            <Bar percent={data.total ? (data.with_three_universities / data.total) * 100 : 0} />
          </div>
        </div>

        <div className="card card-pad">
          <span className="eyebrow">Куда подаются чаще всего</span>
          <div style={{ marginTop: 12 }}>
            {data.popular.map((row) => (
              <div key={row.name} style={{ padding: '7px 0' }}>
                <div className="row-between" style={{ fontSize: 13, marginBottom: 5 }}>
                  <span style={{ fontWeight: 650 }}>{row.name}</span>
                  <b className="num">{row.n}</b>
                </div>
                <Bar percent={(row.n / top) * 100} color="var(--indigo)" />
              </div>
            ))}
            {data.popular.length === 0 && <p className="muted">Списки вузов ещё не заведены.</p>}
          </div>
        </div>
      </div>

      <h2 className="section" id="deadlines">
        Ближайшие дедлайны
      </h2>
      <div className="grid grid--cards">
        {data.deadlines.map((row) => {
          const left = daysLeft(row.deadline)
          const tone = left < 30 ? 'chip-risk' : left < 60 ? 'chip-warn' : 'chip-mute'
          return (
            <div key={row.id} className="card card-pad">
              <div className="row-between">
                <div>
                  <b style={{ fontSize: 14.5 }}>{row.university}</b>
                  <p className="muted" style={{ fontSize: 12.5, margin: '4px 0 0' }}>
                    {row.country} · {row.round_type} · {row.program_name}
                  </p>
                </div>
                <span className={`chip ${tone} num`}>{left} дн</span>
              </div>
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
                <b className="num" style={{ fontSize: 19 }}>
                  {row.applicants_count}
                </b>{' '}
                <span className="muted" style={{ fontSize: 12.5 }}>
                  учеников подаются
                </span>
              </div>
            </div>
          )
        })}
        {data.deadlines.length === 0 && <p className="muted">Дедлайнов в ближайшие 120 дней нет.</p>}
      </div>

      <h2 className="section">Пробелы</h2>
      <div className="grid grid--two">
        <ListPanel
          title="Нет Common App"
          rows={data.no_common_app}
          onOpen={(id) => navigate(`/students/${id}`)}
          right={(row) => <span className="chip chip-mute">{row.status || '—'}</span>}
        />
        <ListPanel
          title="Нет application account"
          rows={data.no_application_account}
          onOpen={(id) => navigate(`/students/${id}`)}
        />
      </div>
    </div>
  )
}
