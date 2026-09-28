/**
 * Полоса прогресса.
 *
 * Образец — `prog()` из `docs/ui/reference.html` и полоса
 * «Отвечено 2 из 6» в `docs/ui/language/Survey.html`: дорожка `--track`,
 * заливка `--accent` (или тон good/warn/bad/info), высота 6 и скругление
 * `--radius-pill`, справа число «N %» размером `.t-value`.
 *
 * Процент приходит готовым — с сервера, уже в процентах — и здесь только
 * ограничивается нулём и сотней. Умножать, делить и считать нечего.
 */
export type ProgressTone = 'accent' | 'good' | 'warn' | 'bad' | 'info'

export default function Progress({
  percent,
  tone = 'accent',
  label = true,
  className,
}: {
  /** уже в процентах, от 0 до 100 */
  percent: number
  tone?: ProgressTone
  /** число справа от полосы; без него — одна полоса */
  label?: boolean
  className?: string
}) {
  const shown = Number.isFinite(percent) ? Math.min(100, Math.max(0, percent)) : 0
  const rounded = Math.round(shown)
  return (
    <div
      className={`prog${className ? ` ${className}` : ''}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={rounded}
    >
      <span className="prog__track">
        <i className={`prog__fill prog__fill--${tone}`} style={{ width: `${shown}%` }} />
      </span>
      {label && <span className="prog__value t-value num">{rounded}&nbsp;%</span>}
    </div>
  )
}
