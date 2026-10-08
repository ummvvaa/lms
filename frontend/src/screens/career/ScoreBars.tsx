/**
 * Баллы по шкалам теста по убыванию (образец владельца): длина полоски — от
 * наименьшего возможного балла шкалы к наибольшему, плюс и минус видны оба;
 * в разбор ИИ идут только шкалы не ниже порога теста. На широком экране —
 * таблица, на телефоне и в узкой панели — компактный список: четыре колонки
 * в 330 пикселей ломали названия шкал по буквам.
 */
import DataTable, { type Column } from '../../components/DataTable'
import { Bar, Chip } from '../../components/ui'
import { t } from '../../i18n'
import { usePhone } from '../../phone'
import type { CareerScore } from '../../api/career'

function percentOf(row: CareerScore): number {
  const span = row.high - row.low
  if (span <= 0) return 0
  return ((row.score - row.low) / span) * 100
}

const colorOf = (row: CareerScore, threshold: number) => (row.score >= threshold ? 'var(--accent)' : 'var(--ink-4)')

export default function ScoreBars({ scores, threshold, limit, compact = false }: { scores: CareerScore[]; threshold: number; limit?: number; compact?: boolean }) {
  const phone = usePhone()
  if (compact || phone) {
    return (
      <div className="cbars">
        {scores.map((row) => (
          <div key={row.scale} className="cbars__row">
            <div className="cbars__head">
              <span className="cbars__title">{row.title}</span>
              <b className="num">{row.score}</b>
            </div>
            <Bar percent={percentOf(row)} color={colorOf(row, threshold)} />
            {row.label && (
              <Chip size="sm" tone={row.score >= threshold ? 'accent' : 'neutral'}>
                {row.label}
              </Chip>
            )}
          </div>
        ))}
      </div>
    )
  }
  const columns: Column<CareerScore>[] = [
    { key: 'title', title: t('Шкала'), width: '30%', cell: (row) => <span className="cbars__title">{row.title}</span>, sortBy: (row) => row.title },
    {
      key: 'bar',
      title: t('Балл'),
      width: '34%',
      cell: (row) => (
        <span className="cbars__bar">
          <Bar percent={percentOf(row)} color={colorOf(row, threshold)} />
        </span>
      ),
    },
    { key: 'score', title: t('Число'), width: '10%', align: 'right', cell: (row) => <b className="num">{row.score}</b>, sortBy: (row) => row.score },
    {
      key: 'label',
      title: t('Интерпретация'),
      width: '26%',
      cell: (row) =>
        row.label ? (
          <Chip size="sm" tone={row.score >= threshold ? 'accent' : 'neutral'}>
            {row.label}
          </Chip>
        ) : (
          <span className="t-note">{t('нет')}</span>
        ),
    },
  ]
  return <DataTable columns={columns} rows={scores} rowKey={(row) => row.scale} fit limit={limit} />
}
