/**
 * Записи портфолио плитками, как в макете: слева значок или дата,
 * название и подпись, справа результат и состояние чипом.
 *
 * Читают «Портфолио» 11 (вкладки) и разделы 8–10 «Олимпиады» и «Спорт».
 * Данные те же, что раньше шли в `RowsList`: отправленные и ждущие решения
 * записи стоят первыми с пометкой «на проверке у директора», внесённые
 * куратором — с пометкой «внёс куратор».
 */
import type { ReactNode } from 'react'
import { ByCurator } from '../components/PortfolioForms'
import { Chip, DataCard, type Tone } from '../components/ui'
import type { Domain } from '../api/types'
import Icon from '../layout/icons'
import { t } from '../i18n'
import { monthName } from '../lib/format'

export interface Entry {
  key: string | number
  title: string
  meta?: string
  /** итог участия: место, диплом — крупнее подписи */
  result?: string
  /** дата плиткой «12 окт.» или значок слева */
  lead?: ReactNode
  state?: { label: string; tone: Tone }
  byCurator?: boolean
}

/** Отправленная и ещё не решённая запись — одна пометка на все разделы. */
export const waitingState = (): { label: string; tone: Tone } => ({
  label: t('на проверке у директора'),
  tone: 'warn',
})

/** Значок медали в кружке — у олимпиад и достижений. */
export const Medal = ({ on = false }: { on?: boolean }) => (
  <span className={`pfl-medal${on ? ' pfl-medal--on' : ''}`} aria-hidden="true">
    <Icon name="medal" size={18} />
  </span>
)

/** Дата плиткой: число крупно, месяц коротко. Без даты — значок. */
export function DateTile({ value }: { value: string | null }) {
  if (!value) return <Medal />
  const [, month, day] = value.split('-').map(Number)
  return (
    <span className="pfl-date" aria-hidden="true">
      <b className="num">{day}</b>
      <span>{monthName(month - 1, 'short')}</span>
    </span>
  )
}

export function EntryList({ rows, empty }: { rows: Entry[]; empty: string }) {
  if (rows.length === 0) return <p className="muted rows__empty">{empty}</p>
  return (
    <ul className="pfl-list">
      {rows.map((row) => (
        <li key={row.key} className={`rows__item pfl-entry${row.lead ? '' : ' pfl-entry--bare'}`}>
          {row.lead}
          <span className="pfl-entry__what">
            <span className="rows__label pfl-entry__title">{row.title}</span>
            {row.meta && <span className="pfl-entry__meta">{row.meta}</span>}
          </span>
          <span className="pfl-entry__result">{row.result}</span>
          <span className="pfl-entry__state">
            {row.byCurator && <ByCurator />}
            {row.state && <Chip tone={row.state.tone}>{row.state.label}</Chip>}
          </span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Владелец домена — его имя в «Кто подтверждает». `of` — код домена
 * («documents») или метка модели («students.Activity»): тогда домен тот,
 * в который модель входит по реестру.
 */
export function ownerOf(domains: Domain[], of: string): string {
  const domain = of.includes('.')
    ? domains.find((d) => d.models.some((m) => m.label === of))
    : domains.find((d) => d.code === of)
  return domain?.owner_name ?? ''
}

/** Правая карточка вкладки: кто подтверждает и что будет после. */
export function WhoConfirms({ owner }: { owner: string }) {
  return (
    <DataCard title={t('Кто подтверждает')}>
      <p className="pfl-who">{owner ? t('Вносите сами, подтверждает {owner}', { owner }) : t('Вносите сами')}</p>
      <p className="muted t-note">{t('Запись попадёт в карточку и CV после подтверждения. Если вернут — причина будет вверху экрана.')}</p>
    </DataCard>
  )
}
