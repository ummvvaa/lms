/**
 * Пробники ученика 8–10 в карточке сотрудника (решение владельца, 30.09.2026).
 *
 * Пробники IELTS и SAT сотрудники ведут у всех параллелей, а домен
 * «экзамены» — цели, официальные попытки, текущий балл — только у 11
 * (`core/parallels.py`, `MOCK_PARALLELS`). Поэтому у 8–10 в карточке
 * нет блока экзаменов, но есть этот: пробники из файла и внесённые руками.
 * Ученик 8–10 его не видит — раздел экзаменов у него закрыт целиком.
 *
 * Форма и путь те же, что у 11 (`RowsSection`, `/attempts/`): формат
 * сдачи здесь всегда «пробник», сервер официальную попытку 8–10 не примет.
 */
import { toast } from 'sonner'
import { useAttemptRows, useMockAttempts } from '../api/hooks'
import { t } from '../i18n'
import { type FieldDef, type RowValues } from '../components/RowForm'
import { RowsSection } from '../components/StudentRows'
import { ErrorNote, Loading } from '../components/ui'
import { formatDate } from '../lib/format'

/** Экзамены пробников — те же два, что у загрузки файлом. */
const MOCK_EXAMS = ['IELTS', 'SAT'].map((value) => ({ value, title: value }))
const IELTS_SECTIONS = ['listening', 'reading', 'writing', 'speaking'] as const

const dateOf = (value: string | null | undefined) => (value ? formatDate(value) : '')
const text = (value: RowValues[string] | undefined) => (value === null || value === undefined ? '' : String(value))
const numberOrNull = (value: RowValues[string] | undefined) => (text(value) === '' ? null : Number(value))

export default function MockAttempts({
  studentId,
  role,
  mayWrite,
  mayRemove,
  note,
  invalidate,
  onSaved,
}: {
  studentId: number
  role: string
  /** право с сервера (куратор — карта `enters`); не задано — по владельцу таблицы */
  mayWrite?: boolean
  mayRemove?: boolean
  note?: string
  invalidate?: string[][]
  onSaved?: () => void
}) {
  const rows = useMockAttempts(studentId)
  const attempts = useAttemptRows()

  if (rows.isLoading) return <Loading kind="table" />
  if (rows.isError) return <ErrorNote error={rows.error} />

  const fields: FieldDef[] = [
    { name: 'exam_type', label: 'Экзамен', kind: 'select', options: MOCK_EXAMS, required: true },
    { name: 'date', label: 'Дата пробника', kind: 'date', required: true },
    { name: 'total_score', label: 'Общий балл', kind: 'number', required: true },
    ...IELTS_SECTIONS.map((name): FieldDef => ({
      name,
      label: `${name[0].toUpperCase()}${name.slice(1)} — ${t('секция IELTS')}`,
      kind: 'number',
    })),
  ]
  const body = (values: RowValues) => ({
    exam_type: text(values.exam_type),
    attempt_format: 'mock',
    date: text(values.date),
    total_score: numberOrNull(values.total_score),
    ...Object.fromEntries(IELTS_SECTIONS.map((name) => [name, numberOrNull(values[name])])),
  })
  const done = { onSuccess: () => onSaved?.(), onError: (e: Error) => toast.error(e.message) }

  return (
    <RowsSection
      title={t('Пробники')}
      note={note}
      hint={t(
        'Пробники IELTS и SAT ведутся у всех параллелей. Цели, официальные баллы и поступление — только у 11. Пробник из файла здесь не правится: неверный файл убирают в архив и загружают заново.',
      )}
      model="students.ExamAttempt"
      path="/attempts/"
      role={role}
      mayWrite={mayWrite}
      mayRemove={mayRemove}
      invalidate={invalidate}
      empty={t('пробников ещё не было')}
      fields={fields}
      addLabel={t('Внести пробник')}
      busy={attempts.create.isPending || attempts.update.isPending}
      onCreate={(values) => attempts.create.mutate({ student: studentId, ...body(values) }, done)}
      onUpdate={(id, values) => attempts.update.mutate({ id, ...body(values) }, done)}
      rows={[...(rows.data?.results ?? [])].reverse().map((row) => ({
        id: row.id,
        label: `${row.exam_type} ${row.total_score ?? t('без балла')}`,
        note: [
          dateOf(row.date),
          row.mock_import ? t('пробник из файла') : t('пробник, внесён руками'),
          row.mock_teacher ? `${t('учитель')} ${row.mock_teacher}` : '',
        ]
          .filter(Boolean)
          .join(' · '),
        byCurator: (row.entered_by_curator ?? []).length > 0,
        // пробник из файла руками не правится — ни куратором, ни Кымбат
        locked: Boolean(row.mock_import),
        values: {
          exam_type: row.exam_type,
          date: row.date,
          total_score: row.total_score ?? '',
          ...Object.fromEntries(IELTS_SECTIONS.map((name) => [name, row[name] ?? ''])),
        },
      }))}
    />
  )
}
