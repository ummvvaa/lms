/**
 * Карточка строки справочника, которую видит ученик: сюжет главной, бейдж.
 *
 * Таблица с пятью колонками здесь не работала: заголовок и описание
 * переносились в три строки и не читались, а условие показа терялось среди
 * служебных колонок. Карточка показывает запись так, как её увидит ученик, —
 * заголовок и подпись, — а под ними строкой говорит, когда она показывается
 * и куда ведёт. «Показывать» переключается прямо здесь, порядок меняется
 * стрелками: числового поля, в которое надо придумывать 30 или 35, нет.
 */
import type { ReactNode } from 'react'
import { ArrowDownIcon, ArrowUpIcon } from 'lucide-react'
import { Button } from './ui/button'
import { Switch } from './ui/switch'
import { t } from '../i18n'

export default function SettingCard({
  title,
  subtitle,
  tone,
  facts,
  shown,
  onShown,
  busy,
  onUp,
  onDown,
  menu,
  children,
}: {
  /** заголовок и подпись — как увидит ученик */
  title: string
  subtitle?: string
  /** цвет полосы слева: тот же, что у карточки на главной ученика */
  tone?: string
  /** строки «Показывается, когда: …», «Ведёт на: …», «Даётся за: …» */
  facts: { label: string; value: ReactNode }[]
  shown: boolean
  onShown: (next: boolean) => void
  busy?: boolean
  /** порядок стрелками; `undefined` — стрелки нет (первая или последняя карточка),
   *  обе не заданы — у справочника нет порядка */
  onUp?: () => void
  onDown?: () => void
  menu?: ReactNode
  /** правка на месте: например, порог бейджа */
  children?: ReactNode
}) {
  const ordered = onUp !== undefined || onDown !== undefined
  return (
    <article className={`scard${shown ? '' : ' scard--hidden'}${tone ? ` scard--${tone}` : ''}`}>
      <div className="scard__body">
        <h3 className="scard__title">{title}</h3>
        {subtitle && <p className="scard__sub">{subtitle}</p>}
        <dl className="scard__facts">
          {facts.map((fact) => (
            <div key={fact.label} className="scard__fact">
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
        {children}
      </div>
      <div className="scard__side">
        <label className="scard__switch">
          <Switch
            checked={shown}
            disabled={busy}
            aria-label={`${t('Показывать')}: ${title}`}
            onCheckedChange={onShown}
          />
          <span>{shown ? t('показывается') : t('скрыт')}</span>
        </label>
        <div className="scard__tools">
          {ordered && (
            <>
              <Button
                variant="ghost"
                size="icon"
                disabled={busy || onUp === undefined}
                aria-label={`${t('Выше')}: ${title}`}
                onClick={onUp}
              >
                <ArrowUpIcon />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                disabled={busy || onDown === undefined}
                aria-label={`${t('Ниже')}: ${title}`}
                onClick={onDown}
              >
                <ArrowDownIcon />
              </Button>
            </>
          )}
          {menu}
        </div>
      </div>
    </article>
  )
}
