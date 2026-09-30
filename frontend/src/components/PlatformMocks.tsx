/**
 * Платформенные моки — отдельным списком у академического директора.
 *
 * Балл, полученный на платформе, сам по себе текущий балл ученика не меняет:
 * решение «учитывать» принимает человек, и оно уходит в журнал.
 */
import { useState } from 'react'
import { usePlatformMocks, useReviewMock } from '../api/hooks'
import { t } from '../i18n'
import { Button } from './ui/button'
import DataTable from './DataTable'
import { Chip } from './ui'
import { formatDate } from '../lib/format'

/**
 * Столько строк показываем сразу. На школе в 250 человек этот список
 * иначе занимает весь дашборд, а решать надо по тем, что ждут решения.
 */
const VISIBLE = 10

export default function PlatformMocks() {
  const mocks = usePlatformMocks()
  const review = useReviewMock()
  const [all, setAll] = useState(false)

  const rows = mocks.data ?? []
  if (rows.length === 0) return null

  const waiting = rows.filter((row) => !row.counted_in_profile && !row.reviewed_at)
  // сверху то, что ждёт решения: просмотренное листать незачем
  const ordered = [...waiting, ...rows.filter((row) => !waiting.includes(row))]
  const shown = all ? ordered : ordered.slice(0, VISIBLE)
  type MockRow = (typeof shown)[number]

  return (
    <div className="card card-pad queue" id="platform-mocks">
      <span className="eyebrow">{t('Пробные, пройденные на платформе')}</span>
      <p className="muted queue__note">
        {waiting.length > 0
          ? `${waiting.length} ждут вашего решения. Текущий балл ученика пробники не меняют — отметка говорит, что результат вы сверили.`
          : 'Все результаты просмотрены.'}
      </p>
      <DataTable
        columns={[
          { key: 'when', title: t('Дата'), width: '12%', cell: (row: MockRow) => <span className="num">{formatDate(row.created_at)}</span>, sortBy: (row: MockRow) => row.created_at },
          { key: 'student', title: t('Ученик'), width: '24%', cell: (row: MockRow) => <b>{row.student_name}</b>, sortBy: (row: MockRow) => row.student_name },
          { key: 'mock', title: t('Пробный'), width: '18%', cell: (row: MockRow) => row.mock },
          {
            key: 'score',
            title: t('Балл'),
            width: '14%',
            align: 'right',
            cell: (row: MockRow) => (
              <span className="num">
                {row.score ?? t('нет')} <span className="t-note">({row.correct}/{row.total})</span>
              </span>
            ),
            sortBy: (row: MockRow) => row.score,
          },
          {
            key: 'state',
            title: t('Состояние'),
            width: '14%',
            cell: (row: MockRow) =>
              row.counted_in_profile ? <Chip tone="good" size="sm">{t('засчитан')}</Chip> : row.reviewed_at ? <Chip size="sm">{t('не засчитан')}</Chip> : <Chip tone="warn" size="sm">{t('ждёт решения')}</Chip>,
          },
          {
            key: 'acts',
            title: '',
            width: '18%',
            align: 'right',
            cell: (row: MockRow) => (
              <span className="acad__inline">
                <Button size="sm" disabled={review.isPending || row.counted_in_profile} onClick={() => review.mutate({ id: row.id, count_it: true })}>
                  {t('Засчитать')}
                </Button>
                <Button variant="outline" size="sm" disabled={review.isPending} onClick={() => review.mutate({ id: row.id, count_it: false })}>
                  {t('Не засчитывать')}
                </Button>
              </span>
            ),
          },
        ]}
        rows={shown}
        rowKey={(row) => row.id}
      />
      {ordered.length > VISIBLE && (
        <Button variant="outline" size="sm" className="queue__more" onClick={() => setAll(!all)}>
          {all ? 'Свернуть' : `Показать все — ещё ${ordered.length - VISIBLE}`}
        </Button>
      )}
    </div>
  )
}
