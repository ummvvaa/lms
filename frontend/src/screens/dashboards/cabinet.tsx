/**
 * Общая часть шести кабинетов (фаза 49).
 *
 * Ряд карточек-чисел сверху и раскладка «две трети — треть» ниже:
 * слева то, чем директор занят каждый день, справа — то, на что он
 * оглядывается. Экраны при этом разные, а не один с подменой данных:
 * общее здесь ровно то, что и правда общее.
 */
import { Fragment, type ReactNode } from 'react'
import { StatRow } from '../../components/patterns'
import { Kpi, type Tone } from '../../components/ui'
import type { CabinetStat } from '../../api/hooks'
import { t } from '../../i18n'
import './cabinet.css'

/** Ряд показателей кабинета: три-четыре числа одинаковой высоты. */
export function CabinetStats({ stats }: { stats: CabinetStat[] }) {
  return (
    <StatRow>
      {stats.map((stat) => (
        <Kpi
          key={stat.code}
          tone={(stat.tone as Tone) ?? 'neutral'}
          label={t(stat.label)}
          value={stat.value}
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

/**
 * Карточка дашборда для раскладки по колонкам (фаза 80).
 *
 * Дашборд называет карточки в порядке важности для роли и говорит про каждую:
 * где её место, сколько в ней примерно строк и не пуста ли она. Куда карточка
 * встанет на самом деле, решает `CabinetBoard`.
 */
export interface BoardCard {
  key: string
  /** место по смыслу: длинные списки — в широкой колонке, короткие сводки — в узкой */
  column: 'main' | 'aside'
  /** примерная высота в строках списка: по ней уравниваются колонки */
  rows: number
  /** карточке нечего показать — она рисуется одной строкой и уходит вниз */
  folded?: boolean
  /** читается и в узкой колонке: такую можно переставить направо, если там пусто */
  narrow?: boolean
  node: ReactNode
}

/** Шапка карточки в тех же «строках», что и список: заголовок, подпись, отступы. */
const HEAD_ROWS = 2
const LIST_ROWS = 5

/** Высота карточки в строках: список длиннее пяти свёрнут под «Показать все». */
const weigh = (card: BoardCard) => (card.folded ? 1 : HEAD_ROWS + Math.min(card.rows, LIST_ROWS + 1))

/**
 * Две колонки примерно одной высоты (фаза 80).
 *
 * Раньше колонки собирались руками в каждом дашборде, и пустая карточка
 * занимала столько же места, сколько полная: справа три заголовка над
 * пустотой, слева очередь на два экрана. Теперь правила одни:
 *
 * - живые карточки стоят в своей колонке в порядке важности;
 * - колонка без живых карточек не остаётся: направо переезжает последняя
 *   из тех, что читаются в узкой колонке, налево — первая из правых;
 * - пустые карточки (одна строка) уходят вниз той колонки, что короче:
 *   они наименее важны и заодно подравнивают высоту.
 *
 * На телефоне колонка одна: широкая, за ней узкая — тот же порядок по важности.
 */
export function CabinetBoard({ cards }: { cards: (BoardCard | null | false | undefined)[] }) {
  const all = cards.filter((card): card is BoardCard => Boolean(card))
  const live = all.filter((card) => !card.folded)
  let main = live.filter((card) => card.column === 'main')
  let aside = live.filter((card) => card.column === 'aside')

  if (aside.length === 0 && main.length > 1) {
    const moved = [...main].reverse().find((card) => card.narrow)
    if (moved) {
      main = main.filter((card) => card !== moved)
      aside = [moved]
    }
  }
  // единственная живая карточка — тоже налево: широкая колонка не стоит из одних пустых строк
  if (main.length === 0 && aside.length > 0) {
    main = [aside[0]]
    aside = aside.slice(1)
  }

  const height = (column: BoardCard[]) => column.reduce((sum, card) => sum + weigh(card), 0)
  for (const card of all.filter((item) => item.folded)) {
    if (height(aside) < height(main)) aside = [...aside, card]
    else main = [...main, card]
  }

  return (
    <div className="cabinet__cols">
      <div className="cabinet__main">
        {main.map((card) => (
          <Fragment key={card.key}>{card.node}</Fragment>
        ))}
      </div>
      <div className="cabinet__aside">
        {aside.map((card) => (
          <Fragment key={card.key}>{card.node}</Fragment>
        ))}
      </div>
    </div>
  )
}
