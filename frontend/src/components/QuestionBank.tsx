/**
 * Банк вопросов и пробные экзамены — хозяйство академического директора.
 *
 * До фазы 31 экрана не было ни у кого: задания заводились только через
 * админку Django, а собрать пробный можно было тем же путём. Тренировки
 * и моки при этом собираются именно из банка — то есть половина раздела
 * подготовки зависела от того, пустят ли человека в админку.
 */
import { useState } from 'react'
import {
  useBankOverview,
  useMockExams,
  useMockRows,
  useQuestionRows,
  useQuestions,
  type BankQuestion,
  type MockWrite,
} from '../api/hooks'
import DataTable, { type Column } from './DataTable'
import DeleteButton from './DeleteButton'
import Empty from './Empty'
import Modal from './Modal'
import RowForm, { type FieldDef, type RowValues } from './RowForm'
import { counted, DataCard, ErrorNote, Loading, Metric, MetricRow } from './ui'
import { t } from '../i18n'
import { SelectField } from './SelectField'
import { Button } from './ui/button'
import RowMenu, { RowMenuItem, RowMenuSeparator } from './RowMenu'

const EXAM_TYPES = ['IELTS', 'TOEFL', 'SAT', 'ACT'].map((value) => ({ value, title: value }))

const SECTIONS = [
  { value: 'listening', title: 'Listening' },
  { value: 'reading', title: 'Reading' },
  { value: 'writing', title: 'Writing' },
  { value: 'speaking', title: 'Speaking' },
  { value: 'math', title: 'Math' },
  { value: 'verbal', title: 'Verbal' },
]

const DIFFICULTIES = [
  { value: 'easy', title: 'Простое' },
  { value: 'medium', title: 'Среднее' },
  { value: 'hard', title: 'Сложное' },
]

const LETTERS = ['A', 'B', 'C', 'D']

/** Варианты ответа: четыре строки плюс отметка верного. */
const OPTION_FIELDS: FieldDef[] = LETTERS.flatMap((letter) => [
  { name: `option_${letter}`, label: `Вариант ${letter}`, kind: 'text' as const },
])

export function QuestionBank() {
  const [filters, setFilters] = useState({ exam_type: '', section: '', difficulty: '' })
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<BankQuestion | null>(null)

  const bank = useBankOverview()
  const list = useQuestions(filters)
  const rows = useQuestionRows()

  const fields: FieldDef[] = [
    { name: 'exam_type', label: 'Экзамен', kind: 'select', options: EXAM_TYPES, required: true },
    { name: 'section', label: 'Секция', kind: 'select', options: SECTIONS, required: true },
    { name: 'topic', label: 'Тема', kind: 'text', required: true },
    { name: 'difficulty', label: 'Сложность', kind: 'select', options: DIFFICULTIES, required: true },
    { name: 'text', label: 'Текст задания', kind: 'textarea', required: true },
    ...OPTION_FIELDS,
    {
      name: 'correct',
      label: 'Верный вариант',
      kind: 'select',
      options: LETTERS.map((l) => ({ value: l, title: l })),
    },
    { name: 'explanation', label: 'Объяснение для разбора', kind: 'textarea' },
    { name: 'source', label: 'Источник', kind: 'text' },
  ]

  const body = (values: RowValues) => ({
    exam_type: String(values.exam_type),
    section: String(values.section),
    topic: String(values.topic ?? ''),
    difficulty: String(values.difficulty ?? 'medium'),
    text: String(values.text ?? ''),
    explanation: String(values.explanation ?? ''),
    source: String(values.source ?? ''),
    options: LETTERS.filter((letter) => String(values[`option_${letter}`] ?? '').trim() !== '').map(
      (letter) => ({
        letter,
        text: String(values[`option_${letter}`]),
        is_correct: values.correct === letter,
      }),
    ),
  })

  const table = list.data?.results ?? []

  const columns: Column<BankQuestion>[] = [
    {
      key: 'topic',
      title: t('Тема'),
      width: '22%',
      cell: (row) => <b>{row.topic}</b>,
      sortBy: (row) => row.topic.toLowerCase(),
    },
    {
      key: 'exam',
      title: t('Экзамен'),
      width: '10%',
      cell: (row) => row.exam_type,
      sortBy: (row) => row.exam_type,
    },
    {
      key: 'section',
      title: t('Секция'),
      width: '12%',
      cell: (row) => SECTIONS.find((s) => s.value === row.section)?.title ?? row.section,
      sortBy: (row) => row.section,
    },
    {
      key: 'difficulty',
      title: t('Сложность'),
      width: '11%',
      cell: (row) => DIFFICULTIES.find((d) => d.value === row.difficulty)?.title ?? row.difficulty,
      // от простого к сложному, а не по алфавиту
      sortBy: (row) => DIFFICULTIES.findIndex((d) => d.value === row.difficulty),
    },
    { key: 'text', title: t('Задание'), width: '25%', cell: (row) => row.text },
    {
      key: 'actions',
      title: '',
      width: '64px',
      align: 'right',
      cell: (row) => (
        <RowMenu>
          <RowMenuItem onClick={() => setEditing(row)}>{t('Изменить')}</RowMenuItem>
          <RowMenuSeparator />
          <RowMenuItem risk keepOpen>
            <DeleteButton
              inMenu
              model="prep.Question"
              id={row.id}
              path="/prep/questions/"
              invalidate={[['prep-questions'], ['prep-bank']]}
            />
          </RowMenuItem>
        </RowMenu>
      ),
    },
  ]

  return (
    <DataCard
      title={t('Банк заданий')}
      note={t('Из него собираются тренировки и пробные')}
      count={bank.data?.total ?? 0}
      right={
        <Button size="sm" onClick={() => setAdding(true)}>
          {t('Завести задание')}
        </Button>
      }
    >
      <div className="toolbar">
        {(
          [
            ['exam_type', 'Все экзамены', EXAM_TYPES],
            ['section', 'Все секции', SECTIONS],
            ['difficulty', 'Любая сложность', DIFFICULTIES],
          ] as const
        ).map(([name, blank, options]) => (
          <SelectField
            key={name}
            aria-label={t(blank)}
            value={filters[name]}
            onChange={(event) => setFilters({ ...filters, [name]: event.target.value })}
          >
            <option value="">{t(blank)}</option>
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.title}
              </option>
            ))}
          </SelectField>
        ))}
        <span className="toolbar__spacer" />
        <span className="muted">{counted(list.data?.count ?? 0, ['задание', 'задания', 'заданий'])}</span>
      </div>

      {list.isLoading && <Loading kind="table" />}
      {list.error && <ErrorNote error={list.error} />}

      <DataTable
        columns={columns}
        rows={table}
        rowKey={(row) => row.id}
        empty={
          <Empty
            icon="target"
            title={t('Заданий пока нет')}
            what={t('Заведите первое — из банка собираются тренировки и пробные.')}
            hint={t(
              'У задания есть тема, секция и сложность: по ним тренировка подбирает вопросы, а разбор показывает объяснение.',
            )}
            action={t('Завести задание')}
            onAction={() => setAdding(true)}
          />
        }
      />

      {(adding || editing) && (
        <Modal
          title={editing ? t('Изменить задание') : t('Новое задание')}
          note={t('Отметьте верный вариант — его считает сервер, ученику он не отдаётся')}
          onClose={() => {
            setAdding(false)
            setEditing(null)
          }}
        >
          <RowForm
            fields={fields}
            row={
              editing
                ? {
                    exam_type: editing.exam_type,
                    section: editing.section,
                    topic: editing.topic,
                    difficulty: editing.difficulty,
                    text: editing.text,
                    explanation: editing.explanation,
                    source: editing.source,
                    correct: editing.options.find((option) => option.is_correct)?.letter ?? '',
                    ...Object.fromEntries(
                      LETTERS.map((letter) => [
                        `option_${letter}`,
                        editing.options.find((option) => option.letter === letter)?.text ?? '',
                      ]),
                    ),
                  }
                : { exam_type: 'IELTS', difficulty: 'medium' }
            }
            busy={rows.create.isPending || rows.update.isPending}
            submitLabel={editing ? t('Сохранить') : t('Завести')}
            onCancel={() => {
              setAdding(false)
              setEditing(null)
            }}
            onSubmit={(values) => {
              if (editing) rows.update.mutate({ id: editing.id, ...body(values) })
              else rows.create.mutate(body(values))
              setAdding(false)
              setEditing(null)
            }}
          />
        </Modal>
      )}
    </DataCard>
  )
}

/** Пробные экзамены: секции и ограничение по времени. */
export function MockExams() {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const mocks = useMockExams()
  const rows = useMockRows()

  const list = mocks.data?.results ?? []
  const current = list.find((row) => row.id === editing) ?? null

  const fields: FieldDef[] = [
    { name: 'title', label: 'Название', kind: 'text', required: true },
    { name: 'exam_type', label: 'Экзамен', kind: 'select', options: EXAM_TYPES, required: true },
    { name: 'time_limit_minutes', label: 'Минут на весь мок', kind: 'number', required: true },
    { name: 'description', label: 'Описание', kind: 'textarea' },
    ...SECTIONS.map((section) => ({
      name: `count_${section.value}`,
      label: `${section.title}: заданий`,
      kind: 'number' as const,
    })),
  ]

  const body = (values: RowValues): MockWrite => ({
    title: String(values.title ?? ''),
    exam_type: String(values.exam_type),
    time_limit_minutes: Number(values.time_limit_minutes ?? 60),
    description: String(values.description ?? ''),
    sections: SECTIONS.filter((section) => Number(values[`count_${section.value}`] ?? 0) > 0).map(
      (section) => ({
        section: section.value,
        question_count: Number(values[`count_${section.value}`]),
      }),
    ),
  })

  return (
    <DataCard
      title={t('Пробные экзамены')}
      note={t('Секции с ограничением по времени')}
      count={list.length}
      right={
        <Button size="sm" onClick={() => setAdding(true)}>
          {t('Собрать пробный')}
        </Button>
      }
    >
      {list.length === 0 && !adding && (
        <Empty
          icon="target"
          title={t('Пробных экзаменов пока нет')}
          what={t('Соберите первый из заданий банка.')}
          hint={t(
            'Мок — это набор секций с ограничением по времени; задания в него подбираются из банка при каждом прохождении.',
          )}
          action={t('Собрать пробный')}
          onAction={() => setAdding(true)}
        />
      )}

      <ul className="rows__list">
        {list.map((mock) => (
          <li key={mock.id} className="rows__item">
            <div className="rows__body">
              <div>
                <span className="rows__label">{mock.title}</span>
                <span className="muted rows__note">
                  {' '}
                  · {mock.exam_type} · {mock.time_limit_minutes} мин ·{' '}
                  {mock.sections.map((s) => `${s.section_title} ${s.question_count}`).join(', ') ||
                    'без секций'}
                </span>
              </div>
              <div className="rows__actions">
                <RowMenu>
                  <RowMenuItem onClick={() => setEditing(mock.id)}>{t('Изменить')}</RowMenuItem>
                  <RowMenuSeparator />
                  <RowMenuItem risk keepOpen>
                    <DeleteButton
                      inMenu
                      model="prep.MockExam"
                      id={mock.id}
                      path="/prep/mocks/"
                      invalidate={[['prep-mocks'], ['prep-bank']]}
                    />
                  </RowMenuItem>
                </RowMenu>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {(adding || current) && (
        <Modal
          title={current ? t('Изменить пробный') : t('Новый пробный экзамен')}
          note={t('Укажите, сколько заданий брать в каждую секцию')}
          onClose={() => {
            setAdding(false)
            setEditing(null)
          }}
        >
          <RowForm
            fields={fields}
            row={
              current
                ? {
                    title: current.title,
                    exam_type: current.exam_type,
                    time_limit_minutes: current.time_limit_minutes,
                    description: '',
                    ...Object.fromEntries(
                      SECTIONS.map((section) => [
                        `count_${section.value}`,
                        current.sections.find((s) => s.section === section.value)?.question_count ?? '',
                      ]),
                    ),
                  }
                : { exam_type: 'IELTS', time_limit_minutes: 60 }
            }
            busy={rows.create.isPending || rows.update.isPending}
            submitLabel={current ? t('Сохранить') : t('Собрать')}
            onCancel={() => {
              setAdding(false)
              setEditing(null)
            }}
            onSubmit={(values) => {
              if (current) rows.update.mutate({ id: current.id, ...body(values) })
              else rows.create.mutate(body(values))
              setAdding(false)
              setEditing(null)
            }}
          />
        </Modal>
      )}
    </DataCard>
  )
}

/** Короткая сводка банка: сколько заданий и по каким секциям. */
export function BankSummary() {
  const bank = useBankOverview()
  if (!bank.data) return null
  // сводка по секциям: строки банка приходят по темам, здесь их складываем
  const bySection = new Map<string, number>()
  bank.data.rows.forEach((row) => {
    bySection.set(row.section_title, (bySection.get(row.section_title) ?? 0) + row.n)
  })
  return (
    <MetricRow>
      <Metric value={bank.data.total} label={t('Заданий в банке')} />
      {[...bySection.entries()].slice(0, 5).map(([title, count]) => (
        <Metric key={title} value={count} label={title} />
      ))}
    </MetricRow>
  )
}
