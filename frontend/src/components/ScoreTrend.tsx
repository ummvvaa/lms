/**
 * График динамики баллов.
 *
 * Попытки лежат строками (инвариант №5), поэтому график строится по истории,
 * а не по одному полю профиля. Платформенные моки отмечены отдельно: доверие
 * к ним и к официальной сдаче разное.
 */
import type { Attempt } from '../api/hooks'
import { t } from '../i18n'
import { Badge } from './ui/badge'

const SOURCE_TITLE: Record<string, string> = {
  manual: 'внесён руками',
  import: 'импорт',
  platform: 'пройден на платформе',
}

function color(attempt: Attempt): string {
  if (attempt.attempt_format === 'official') return 'var(--ok)'
  return attempt.source === 'platform' ? 'var(--brand)' : 'var(--indigo)'
}

export default function ScoreTrend({ attempts, examType }: { attempts: Attempt[]; examType: string }) {
  const rows = attempts
    .filter((a) => a.exam_type === examType && a.total_score !== null)
    .sort((a, b) => a.date.localeCompare(b.date))

  if (rows.length === 0) {
    return (
      <p className="muted trend__empty">Попыток по {examType} пока нет — они появятся после первого мока.</p>
    )
  }

  const values = rows.map((r) => Number(r.total_score))
  const min = Math.min(...values)
  const max = Math.max(...values)
  // все баллы одинаковые — рисовать «рост от минимума» нечего: линия
  // прижималась к нижнему краю и читалась как падение в ноль
  const flat = max === min
  const span = max - min || 1
  const width = 100
  const height = 46

  const points = rows.map((row, i) => {
    const x = rows.length === 1 ? width / 2 : (i / (rows.length - 1)) * width
    const y = flat ? height / 2 : height - ((Number(row.total_score) - min) / span) * (height - 8) - 4
    return { row, x, y }
  })

  const last = rows[rows.length - 1]
  const previous = rows.length > 1 ? rows[rows.length - 2] : null
  const delta = previous ? Number(last.total_score) - Number(previous.total_score) : null

  return (
    <div className="trend">
      <div className="row-between trend__head">
        <span className="eyebrow">{examType} · динамика</span>
        <span className="num trend__last">
          <b>{last.total_score}</b>
          {delta !== null && (
            <Badge variant={delta < 0 ? 'warn' : 'ok'} className="num trend__delta">
              {delta > 0 ? '+' : ''}
              {delta.toFixed(1)}
            </Badge>
          )}
        </span>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className="trend__chart" preserveAspectRatio="none">
        <polyline
          fill="none"
          stroke="var(--line)"
          strokeWidth="1"
          points={points.map((p) => `${p.x},${p.y}`).join(' ')}
        />
        {points.map((point) => (
          <circle key={point.row.id} cx={point.x} cy={point.y} r="2.4" fill={color(point.row)}>
            <title>
              {point.row.date} · {point.row.total_score} ·{' '}
              {SOURCE_TITLE[point.row.source] ?? point.row.source}
            </title>
          </circle>
        ))}
      </svg>

      {flat && rows.length > 1 && (
        <p className="muted trend__flat">
          Все {rows.length} попыток с одинаковым баллом — динамики пока нет.
        </p>
      )}

      <div className="trend__legend">
        <span>
          <i style={{ background: 'var(--ok)' }} />
          {t(' официальный')}
        </span>
        <span>
          <i style={{ background: 'var(--brand)' }} />
          {t(' мок на платформе')}
        </span>
        <span>
          <i style={{ background: 'var(--indigo)' }} />
          {t(' внесён руками')}
        </span>
      </div>
    </div>
  )
}
