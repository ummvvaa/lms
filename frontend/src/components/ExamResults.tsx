/**
 * Внесение результатов экзаменов — по одному и пачкой.
 *
 * Основной способ, пока ученики не сдают пробные внутри платформы:
 * школа проводит мок на бумаге, а числа кто-то переносит. По одной
 * карточке это неделя работы — значит, работа, которую не сделают.
 * Поэтому здесь есть и одиночная форма, и таблица на весь поток.
 */
import { useState } from 'react'
import { useAttemptRows, useAttemptsBulk, useStudents } from '../api/hooks'
import Modal from './Modal'
import RowForm, { type FieldDef } from './RowForm'
import { Chip, DataCard, ErrorNote } from './ui'
import { t, tk } from '../i18n'
import { SelectField } from './SelectField'
import { Input } from './ui/input'
import { Button } from './ui/button'
import DataTable from './DataTable'
import { todayAlmaty } from '../lib/dates'

const EXAM_TYPES = ['IELTS', 'TOEFL', 'SAT', 'ACT'].map((value) => ({ value, title: value }))

const FORMATS = [
  { value: 'mock', title: tk('Mock Test') },
  { value: 'official', title: tk('Официальный') },
]

/** Секции: у языковых экзаменов свои, у SAT и ACT свои. */
const SECTIONS: Record<string, { name: string; label: string }[]> = {
  IELTS: [
    { name: 'listening', label: 'Listening' },
    { name: 'reading', label: 'Reading' },
    { name: 'writing', label: 'Writing' },
    { name: 'speaking', label: 'Speaking' },
  ],
  TOEFL: [
    { name: 'listening', label: 'Listening' },
    { name: 'reading', label: 'Reading' },
    { name: 'writing', label: 'Writing' },
    { name: 'speaking', label: 'Speaking' },
  ],
  SAT: [
    { name: 'math', label: 'Math' },
    { name: 'verbal', label: 'Verbal' },
  ],
  ACT: [
    { name: 'math', label: 'Math' },
    { name: 'verbal', label: 'Verbal' },
  ],
}

const today = todayAlmaty

interface BulkRow {
  student: number
  name: string
  total: string
  sections: Record<string, string>
}

export default function ExamResults() {
  const [single, setSingle] = useState(false)
  const [bulk, setBulk] = useState(false)
  const [examType, setExamType] = useState('IELTS')
  const [format, setFormat] = useState('mock')
  const [date, setDate] = useState(today())
  const [rows, setRows] = useState<BulkRow[]>([])
  const [report, setReport] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  const students = useStudents({ page_size: 500 })
  const attempts = useAttemptRows()
  const bulkSave = useAttemptsBulk()

  const sections = SECTIONS[examType] ?? []
  const list = students.data?.results ?? []

  const singleFields: FieldDef[] = [
    {
      name: 'student',
      label: t('Ученик'),
      kind: 'select',
      required: true,
      options: list.map((row) => ({ value: String(row.id), title: row.full_name })),
    },
    { name: 'exam_type', label: t('Экзамен'), kind: 'select', options: EXAM_TYPES, required: true },
    { name: 'attempt_format', label: t('Формат'), kind: 'select', options: FORMATS.map((row) => ({ ...row, title: t(row.title) })), required: true },
    { name: 'date', label: t('Дата сдачи'), kind: 'date', required: true },
    { name: 'total_score', label: t('Общий балл'), kind: 'number' },
    { name: 'listening', label: 'Listening', kind: 'number' },
    { name: 'reading', label: 'Reading', kind: 'number' },
    { name: 'writing', label: 'Writing', kind: 'number' },
    { name: 'speaking', label: 'Speaking', kind: 'number' },
    { name: 'math', label: 'Math', kind: 'number' },
    { name: 'verbal', label: 'Verbal', kind: 'number' },
  ]

  function openBulk() {
    setRows(list.map((row) => ({ student: row.id, name: row.full_name, total: '', sections: {} })))
    setReport(null)
    setProblem(null)
    setBulk(true)
  }

  function saveBulk() {
    const filled = rows.filter(
      (row) => row.total.trim() !== '' || Object.values(row.sections).some((value) => value.trim() !== ''),
    )
    if (filled.length === 0) {
      setProblem(t('Ни у кого не проставлен балл — вносить нечего'))
      return
    }
    setProblem(null)
    bulkSave.mutate(
      filled.map((row) => ({
        student: row.student,
        exam_type: examType,
        attempt_format: format,
        date,
        total_score: row.total.trim() || null,
        ...Object.fromEntries(
          Object.entries(row.sections).map(([name, value]) => [name, value.trim() || null]),
        ),
      })),
      {
        onSuccess: (result) => {
          setReport(
            result.rejected.length === 0
              ? result.detail
              : t('{detail}. Не приняты: {list}', {
                  detail: result.detail,
                  list: result.rejected.map((bad) => `${bad.student ?? t('строка {n}', { n: bad.row })} — ${bad.reason}`).join('; '),
                }),
          )
          if (result.rejected.length === 0) setBulk(false)
        },
        onError: (error) => setProblem(error instanceof Error ? error.message : t('Не удалось сохранить')),
      },
    )
  }

  return (
    <DataCard
      title={t('Внести результаты')}
      note={t('По одному или сразу за весь поток')}
      hint={t(
        'Балл, внесённый здесь, попадает в историю попыток ученика и в его динамику. Текущий балл профиля он не меняет: это решение принимаете вы отдельно.',
      )}
      right={
        <span className="rows__actions">
          <Button variant="outline" size="sm" onClick={openBulk}>
            {t('Внести пачкой')}
          </Button>
          <Button size="sm" onClick={() => setSingle(true)}>
            {t('Внести результат')}
          </Button>
        </span>
      }
    >
      {report && (
        <Chip tone="good">
          {report}
        </Chip>
      )}

      {single && (
        <Modal
          title={t('Результат экзамена')}
          note={t('Заполните общий балл или баллы по секциям')}
          onClose={() => setSingle(false)}
        >
          <RowForm
            fields={singleFields}
            row={{ exam_type: 'IELTS', attempt_format: 'mock', date: today() }}
            busy={attempts.create.isPending}
            submitLabel={t('Внести')}
            onCancel={() => setSingle(false)}
            onSubmit={(values) => {
              attempts.create.mutate({
                student: Number(values.student),
                exam_type: String(values.exam_type),
                attempt_format: String(values.attempt_format),
                date: String(values.date),
                total_score: values.total_score === null ? null : Number(values.total_score),
                listening: values.listening === null ? null : Number(values.listening),
                reading: values.reading === null ? null : Number(values.reading),
                writing: values.writing === null ? null : Number(values.writing),
                speaking: values.speaking === null ? null : Number(values.speaking),
                math: values.math === null ? null : Number(values.math),
                verbal: values.verbal === null ? null : Number(values.verbal),
              })
              setSingle(false)
            }}
          />
        </Modal>
      )}

      {bulk && (
        <Modal
          title={t('Результаты за весь поток')}
          note={t('Пустые строки не сохраняются — заполняйте только тех, кто сдавал')}
          onClose={() => setBulk(false)}
          wide
        >
          <div className="toolbar">
            <label className="rowform__field">
              <span className="rowform__label">{t('Экзамен')}</span>
              <SelectField value={examType} onChange={(e) => setExamType(e.target.value)}>
                {EXAM_TYPES.map((row) => (
                  <option key={row.value} value={row.value}>
                    {row.title}
                  </option>
                ))}
              </SelectField>
            </label>
            <label className="rowform__field">
              <span className="rowform__label">{t('Формат')}</span>
              <SelectField value={format} onChange={(e) => setFormat(e.target.value)}>
                {FORMATS.map((row) => (
                  <option key={row.value} value={row.value}>
                    {t(row.title)}
                  </option>
                ))}
              </SelectField>
            </label>
            <label className="rowform__field">
              <span className="rowform__label">{t('Дата сдачи')}</span>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
          </div>

          {problem && (
            <Chip tone="bad">
              {problem}
            </Chip>
          )}

          <DataTable
            columns={[
              { key: 'name', title: t('Ученик'), width: '34%', cell: (row: BulkRow) => row.name },
              {
                key: 'total',
                title: t('Общий балл'),
                width: '14%',
                align: 'right',
                cell: (row: BulkRow) => (
                  <Input
                    className="num cell"
                    aria-label={`${t('Общий балл')} — ${row.name}`}
                    value={row.total}
                    onChange={(event) => setRows((prev) => prev.map((item) => (item.student === row.student ? { ...item, total: event.target.value } : item)))}
                  />
                ),
              },
              ...sections.map((section) => ({
                key: section.name,
                title: section.label,
                width: `${Math.max(8, Math.floor(52 / Math.max(1, sections.length)))}%`,
                align: 'right' as const,
                cell: (row: BulkRow) => (
                  <Input
                    className="num cell"
                    aria-label={`${section.label} — ${row.name}`}
                    value={row.sections[section.name] ?? ''}
                    onChange={(event) =>
                      setRows((prev) => prev.map((item) => (item.student === row.student ? { ...item, sections: { ...item.sections, [section.name]: event.target.value } } : item)))
                    }
                  />
                ),
              })),
            ]}
            rows={rows}
            rowKey={(row) => row.student}
          />

          {rows.length === 0 && <ErrorNote error={new Error(t('Учеников в школе пока нет'))} />}

          <div className="rowform__actions">
            <Button variant="outline" size="sm" onClick={() => setBulk(false)}>
              {t('Отмена')}
            </Button>
            <Button size="sm" disabled={bulkSave.isPending} onClick={saveBulk}>
              {t('Сохранить результаты')}
            </Button>
          </div>
        </Modal>
      )}
    </DataCard>
  )
}
