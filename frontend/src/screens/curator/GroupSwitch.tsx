/**
 * Переключатель групп куратора (фаза 61).
 *
 * «Все мои группы» и чип на каждую. Фильтрует всё: очередь, учеников,
 * счётчики, корзины и задачи. У куратора с одной группой переключателя
 * нет вовсе — выбирать не из чего, а лишний ряд чипов только шумит.
 *
 * На телефоне чипы прокручиваются вбок: три группы в узкую строку
 * не помещаются, а перенос ломает высоту шапки (правила фазы 51).
 */
import { type CuratorGroup } from '../../api/hooks'
import { t } from '../../i18n'
import { ALL } from './state'

export default function GroupSwitch({
  groups,
  value,
  onChange,
}: {
  groups: CuratorGroup[]
  value: string
  onChange: (next: string) => void
}) {
  if (groups.length < 2) return null

  const chip = (code: string, label: string, note?: string) => (
    <button
      key={code}
      type="button"
      className={`gswitch__chip${value === code ? ' gswitch__chip--on' : ''}`}
      aria-pressed={value === code}
      onClick={() => onChange(code)}
    >
      {label}
      {note && <span className="gswitch__note">{note}</span>}
    </button>
  )

  return (
    <div className="gswitch" role="group" aria-label={t('Мои группы')}>
      {chip(ALL, t('Все мои группы'))}
      {groups.map((group) => chip(group.code, group.code, String(group.students)))}
    </div>
  )
}
