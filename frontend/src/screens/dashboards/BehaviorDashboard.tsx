/** Салтанат: заполненность профилей, светофор, риски по посещаемости. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import { Bar, Donut, ErrorNote, Kpi, ListPanel, Loading, ScreenHead } from '../../components/ui'

interface Row {
  student_id: number
  student__last_name: string
  student__first_name: string
  attendance_percent?: number
  homework_percent?: number
  remarks_count?: number
}

interface Data {
  total: number
  filled: number
  traffic: Record<string, number>
  worst_attendance: Row[]
  worst_homework: Row[]
  groups: { code: string; grade: number; students_count: number; critical: number; filled: number }[]
}

export default function BehaviorDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<Data>('behavior')
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const t = data.traffic
  const ok = t.can_execute ?? 0
  const warn = t.needs_supervision ?? 0
  const risk = t.critical ?? 0

  return (
    <div>
      <ScreenHead
        emoji="⚙️"
        title="Профиль и дисциплина"
        subtitle={`Цель дня: ${data.total} из ${data.total} учеников с базовым профилем.`}
      />

      <div className="grid grid--kpi">
        <Kpi
          value={`${data.filled} / ${data.total}`}
          label="Профили заполнены"
          note={`${data.total - data.filled} осталось собрать`}
          color="var(--brand)"
        />
        <Kpi value={ok} label="Работают самостоятельно" color="var(--ok)" />
        <Kpi value={warn} label="Нужен контроль" color="var(--warn)" />
        <Kpi value={risk} label="Ежедневный контроль" color="var(--risk)" />
      </div>

      <div className="split">
        <div className="card card-pad">
          <span className="eyebrow">Светофор по школе</span>
          <div className="row-between" style={{ marginTop: 16 }}>
            <Donut
              segments={[
                { value: ok, color: 'var(--ok)' },
                { value: warn, color: 'var(--warn)' },
                { value: risk, color: 'var(--risk)' },
              ]}
            />
            <div className="legend">
              {[
                ['Работают самостоятельно', 'var(--ok)', ok],
                ['Нужен контроль', 'var(--warn)', warn],
                ['Ежедневный контроль', 'var(--risk)', risk],
              ].map(([label, color, value]) => (
                <div key={String(label)} className="legend__row">
                  <span className="legend__dot" style={{ background: String(color) }} />
                  <span className="muted">{label}</span>
                  <b className="num legend__value">{value}</b>
                </div>
              ))}
            </div>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 18 }}>
            Эти ярлыки видны только сотрудникам. У ученика на экране — задачи и процент готовности.
          </p>
        </div>

        <div id="risks">
          <ListPanel
            title="Худшая посещаемость"
            rows={data.worst_attendance}
            limit={20}
            onOpen={(id) => navigate(`/students/${id}`)}
            right={(row) => <span className="chip chip-risk num">{row.attendance_percent}%</span>}
          />
        </div>
      </div>

      <h2 className="section" id="groups">
        Группы
      </h2>
      <div className="grid grid--cards">
        {data.groups.map((g) => (
          <div key={g.code} className="card card-pad">
            <div className="row-between">
              <b style={{ fontSize: 17 }}>{g.code}</b>
              <span className="chip chip-mute num">{g.students_count} чел.</span>
            </div>
            <div className="row-between" style={{ margin: '14px 0 6px', fontSize: 12.5 }}>
              <span className="muted">Заполненность профилей</span>
              <b className="num">{g.students_count ? Math.round((g.filled / g.students_count) * 100) : 0}%</b>
            </div>
            <Bar percent={g.students_count ? (g.filled / g.students_count) * 100 : 0} />
            {g.critical > 0 && (
              <div style={{ marginTop: 12 }}>
                <span className="chip chip-risk num">{g.critical} в зоне риска</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
