/** Мелкие примитивы интерфейса по дизайн-системе прототипа. */
import type { ReactNode } from 'react'

export function Eyebrow({ children }: { children: ReactNode }) {
  return <span className="eyebrow">{children}</span>
}

export function ScreenHead({
  emoji,
  title,
  subtitle,
  eyebrow,
}: {
  emoji: string
  title: string
  subtitle?: string
  /** надзаголовок; по умолчанию — только плашка-эмодзи, без повтора заголовка */
  eyebrow?: string
}) {
  return (
    <header className="head">
      <Eyebrow>{eyebrow ? `${emoji} ${eyebrow}` : emoji}</Eyebrow>
      <h1 className="head__title">{title}</h1>
      {subtitle && <p className="muted head__sub">{subtitle}</p>}
    </header>
  )
}

type Tone = 'ok' | 'warn' | 'risk' | 'brand' | 'mute' | 'teal' | 'indigo'

export function Chip({ tone = 'mute', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>
}

export function Kpi({
  value,
  label,
  note,
  color = 'var(--ink)',
}: {
  value: ReactNode
  label: string
  note?: string
  color?: string
}) {
  return (
    <div className="card card-pad kpi">
      <div className="num kpi__value" style={{ color }}>
        {value}
      </div>
      <div className="kpi__label">{label}</div>
      {note && <div className="muted kpi__note">{note}</div>}
    </div>
  )
}

export function Bar({ percent, color = 'var(--brand)' }: { percent: number; color?: string }) {
  const width = Math.max(0, Math.min(100, percent))
  return (
    <div className="bar">
      <i style={{ width: `${width}%`, background: color }} />
    </div>
  )
}

/** Кольцо готовности. */
export function Ring({
  percent,
  size = 104,
  color = 'var(--brand)',
  children,
}: {
  percent: number
  size?: number
  color?: string
  children?: ReactNode
}) {
  const r = size / 2 - 8
  const c = 2 * Math.PI * r
  const filled = (Math.max(0, Math.min(100, percent)) / 100) * c
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle className="ring__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="9" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c - filled}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring__inner">{children}</div>
    </div>
  )
}

/** Кольцевая диаграмма распределения. */
export function Donut({
  segments,
  size = 132,
}: {
  segments: { value: number; color: string }[]
  size?: number
}) {
  const r = size / 2 - 11
  const c = 2 * Math.PI * r
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1
  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle className="ring__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="15" />
      {segments.map((segment, i) => {
        const length = (segment.value / total) * c
        const element = (
          <circle
            key={i}
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={segment.color}
            strokeWidth="15"
            strokeDasharray={`${length} ${c - length}`}
            strokeDashoffset={-offset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )
        offset += length
        return element
      })}
    </svg>
  )
}

export interface PersonRow {
  student_id: number
  student__last_name: string
  student__first_name: string
}

export function ListPanel<T extends PersonRow>({
  title,
  rows,
  right,
  limit = 12,
  onOpen,
}: {
  title: string
  rows: T[]
  right?: (row: T) => ReactNode
  limit?: number
  onOpen?: (id: number) => void
}) {
  return (
    <div className="card card-pad">
      <div className="panel__head">
        <span className="panel__title">{title}</span>
        <span className="chip chip-mute num">{rows.length}</span>
      </div>
      <div className="panel__list">
        {rows.length === 0 && <p className="muted panel__empty">Никого — это хорошая новость</p>}
        {rows.slice(0, limit).map((row) => (
          <button key={row.student_id} className="person" onClick={() => onOpen?.(row.student_id)}>
            <span className="person__name">
              {row.student__last_name} {row.student__first_name}
            </span>
            {right?.(row)}
          </button>
        ))}
      </div>
      {rows.length > limit && <p className="muted panel__more">и ещё {rows.length - limit}</p>}
    </div>
  )
}

export function Loading() {
  return <p className="muted">Загрузка…</p>
}

export function ErrorNote({ error }: { error: unknown }) {
  return <p className="chip chip-risk">{error instanceof Error ? error.message : 'Ошибка загрузки'}</p>
}
