/**
 * Платформенные моки — отдельным списком у академического директора.
 *
 * Балл, полученный на платформе, сам по себе текущий балл ученика не меняет:
 * решение «учитывать» принимает человек, и оно уходит в журнал.
 */
import { useState } from 'react'
import { usePlatformMocks, useReviewMock, type MockReviewState } from '../api/hooks'
import { t, tn } from '../i18n'
import { Button } from './ui/button'
import DataTable from './DataTable'
import { Chip, type Tone } from './ui'

/** Цвет решения: подпись приходит с сервера, цвет — по коду */
const REVIEW_TONE: Record<MockReviewState, Tone> = { counted: 'good', rejected: 'neutral', waiting: 'warn' }
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
      <span className="eyebrow">{t('Пройденные Mock Test онлайн')}</span>
      <p className="muted queue__note">
        {waiting.length > 0
          ? tn(
              waiting.length,
              '{n} результат ждёт вашего решения. Текущий балл ученика Mock Test онлайн не меняет — отметка говорит, что результат вы сверили.|{n} результата ждут вашего решения. Текущий балл ученика Mock Test онлайн не меняет — отметка говорит, что результат вы сверили.|{n} результатов ждут вашего решения. Текущий балл ученика Mock Test онлайн не меняет — отметка говорит, что результат вы сверили.',
            )
          : t('Все результаты просмотрены.')}
      </p>
      <DataTable
        columns={[
          { key: 'when', title: t('Дата'), width: '12%', cell: (row: MockRow) => <span className="num">{formatDate(row.created_at)}</span>, sortBy: (row: MockRow) => row.created_at },
          { key: 'student', title: t('Ученик'), width: '24%', cell: (row: MockRow) => <b>{row.student_name}</b>, sortBy: (row: MockRow) => row.student_name },
          { key: 'mock', title: t('Mock Test'), width: '18%', cell: (row: MockRow) => row.mock },
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
              <Chip tone={REVIEW_TONE[row.review_state]} size="sm">{row.review_state_title}</Chip>,
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
          {all ? t('Свернуть') : t('Показать все — ещё {n}', { n: ordered.length - VISIBLE })}
        </Button>
      )}
    </div>
  )
}
