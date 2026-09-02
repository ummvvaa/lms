/**
 * Общая часть шести кабинетов (фаза 49).
 *
 * Ряд карточек-чисел сверху и раскладка «две трети — треть» ниже:
 * слева то, чем директор занят каждый день, справа — то, на что он
 * оглядывается. Экраны при этом разные, а не один с подменой данных:
 * общее здесь ровно то, что и правда общее.
 */
import type { ReactNode } from 'react'
import { StatCard, StatRow } from '../../components/patterns'
import type { CabinetStat } from '../../api/hooks'
import type { IconName } from '../../layout/icons'
import { t } from '../../i18n'
import './cabinet.css'

/** Иконка карточки-числа по её коду: список закрытый, как и сами числа. */
const ICONS: Record<string, IconName> = {
  ielts: 'book',
  sat: 'target',
  drops: 'alert',
  queue: 'bulb',
  match: 'target',
  no_universities: 'cap',
  no_plan: 'checklist',
  supervision: 'alert',
  no_contacts: 'person',
  silent: 'clock',
  group: 'medal',
  review: 'doc',
  library: 'openbook',
  empty: 'alert',
  athletes: 'trophy',
  no_certificate: 'alert',
  students: 'people',
  never: 'clock',
  spend: 'card',
  locks: 'lock',
}

type Tone = 'brand' | 'teal' | 'indigo' | 'ok' | 'warn' | 'risk' | 'mute'

/** Ряд чисел кабинета: три-четыре карточки одинаковой высоты. */
export function CabinetStats({ stats }: { stats: CabinetStat[] }) {
  return (
    <StatRow>
      {stats.map((stat) => (
        <StatCard
          key={stat.code}
          icon={ICONS[stat.code] ?? 'layers'}
          tone={(stat.tone as Tone) ?? 'brand'}
          label={t(stat.label)}
          value={stat.value === null ? '—' : stat.value}
          note={stat.note ? t(stat.note) : undefined}
        />
      ))}
    </StatRow>
  )
}

/** Раскладка кабинета: широкая колонка слева, вспомогательная справа. */
export function CabinetColumns({ main, aside }: { main: ReactNode; aside: ReactNode }) {
  return (
    <div className="cabinet__cols">
      <div className="cabinet__main">{main}</div>
      <div className="cabinet__aside">{aside}</div>
    </div>
  )
}
