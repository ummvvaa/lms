/**
 * Шаблоны задач — из них генерируется роадмап потока.
 *
 * Экрана не было ни у одной роли: шаблоны заводились через админку
 * Django. При этом задачи у всех учеников растут именно из них —
 * то есть директор видел план, который сам не мог ни поправить,
 * ни объяснить, откуда он взялся.
 *
 * Владельца-домена у шаблонов нет: ведёт их любой из пяти директоров,
 * как и сами задачи (`SHARED_WRITERS`).
 */
import { useState } from 'react'
import { useTaskTemplates, useTemplateRows, type TaskTemplate } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import DeleteButton from '../components/DeleteButton'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { Button } from '../components/ui/button'
import RowMenu, { RowMenuItem, RowMenuSeparator } from '../components/RowMenu'

const CATEGORIES = [
  { value: 'test', title: 'Тест' },
  { value: 'essay', title: 'Эссе' },
  { value: 'documents', title: 'Документы' },
  { value: 'university', title: 'Вузы' },
  { value: 'portfolio', title: 'Портфолио' },
  { value: 'finance', title: 'Финансы' },
]

const PRIORITIES = [
  { value: 'high', title: 'Высокий' },
  { value: 'medium', title: 'Средний' },
  { value: 'low', title: 'Низкий' },
]

const MONTHS = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
]

const FIELDS: FieldDef[] = [
  { name: 'title', label: 'Название задачи', kind: 'text', required: true },
  { name: 'category', label: 'Категория', kind: 'select', options: CATEGORIES, required: true },
  { name: 'priority', label: 'Важность', kind: 'select', options: PRIORITIES, required: true },
  { name: 'due_day', label: 'Срок: день', kind: 'number' },
  {
    name: 'due_month',
    label: 'Срок: месяц',
    kind: 'select',
    options: MONTHS.map((title, index) => ({ value: String(index + 1), title })),
  },
  { name: 'grade', label: 'Для класса', kind: 'number' },
  { name: 'graduation_year', label: 'Для выпуска', kind: 'number' },
  { name: 'description', label: 'Описание', kind: 'textarea' },
  { name: 'is_active', label: 'Используется', kind: 'checkbox' },
]

function due(row: TaskTemplate): string {
  if (!row.due_month) return '—'
  return `${row.due_day ?? 1} ${MONTHS[row.due_month - 1]}`
}

export default function TaskTemplates() {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<TaskTemplate | null>(null)
  // строка, которую только что завели или поправили: подсветится и погаснет
  const [flashed, setFlashed] = useState<ReadonlySet<number>>(new Set())
  const list = useTaskTemplates()
  const rows = useTemplateRows()

  const table = list.data?.results ?? []

  const body = (values: RowValues) => ({
    title: String(values.title ?? ''),
    category: String(values.category ?? 'documents'),
    priority: String(values.priority ?? 'medium'),
    description: String(values.description ?? ''),
    due_day: values.due_day === null ? null : Number(values.due_day),
    due_month: values.due_month === null ? null : Number(values.due_month),
    grade: values.grade === null ? null : Number(values.grade),
    graduation_year: values.graduation_year === null ? null : Number(values.graduation_year),
    is_active: Boolean(values.is_active),
  })

  const columns: Column<TaskTemplate>[] = [
    {
      key: 'title',
      title: t('Задача'),
      width: '32%',
      cell: (row) => <b>{row.title}</b>,
      sortBy: (row) => row.title.toLowerCase(),
    },
    {
      key: 'category',
      title: t('Категория'),
      width: '14%',
      cell: (row) => CATEGORIES.find((c) => c.value === row.category)?.title ?? row.category,
      sortBy: (row) => row.category,
    },
    {
      key: 'priority',
      title: t('Важность'),
      width: '12%',
      cell: (row) => PRIORITIES.find((p) => p.value === row.priority)?.title ?? row.priority,
      // сортируем по смыслу, а не по алфавиту: «высокая» важнее «средней»,
      // а в алфавите она после неё
      sortBy: (row) => PRIORITIES.findIndex((p) => p.value === row.priority),
    },
    {
      key: 'due',
      title: t('Срок'),
      width: '13%',
      align: 'right',
      cell: (row) => due(row),
      // сортировка по календарю: месяц старше дня
      sortBy: (row) => (row.due_month === null ? null : row.due_month * 100 + Number(row.due_day ?? 0)),
    },
    {
      key: 'scope',
      title: t('Кому'),
      width: '14%',
      cell: (row) =>
        [row.grade ? `${row.grade} класс` : '', row.graduation_year ? `выпуск ${row.graduation_year}` : '']
          .filter(Boolean)
          .join(', ') || t('всем'),
    },
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
              model="roadmap.TaskTemplate"
              id={row.id}
              path="/task-templates/"
              invalidate={[['task-templates']]}
            />
          </RowMenuItem>
        </RowMenu>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Шаблоны задач')}
        subtitle={t('Из них собирается план у всего потока.')}
        actions={<Button onClick={() => setAdding(true)}>{t('Завести шаблон')}</Button>}
      />

      <div className="toolbar">
        <span className="muted">{counted(table.length, ['шаблон', 'шаблона', 'шаблонов'])}</span>
      </div>

      {list.isLoading && <Loading kind="table" />}
      {list.error && <ErrorNote error={list.error} />}

      {!list.isLoading && table.length === 0 && (
        <Empty
          icon="checklist"
          title={t('Шаблонов пока нет')}
          what={t('Заведите первый — по нему план появится у всего потока.')}
          hint={t(
            'Шаблон превращается в задачу при генерации роадмапа: срок берётся из дня и месяца, а «кому» сужает его до класса или года выпуска.',
          )}
          action={t('Завести шаблон')}
          onAction={() => setAdding(true)}
        />
      )}

      {table.length > 0 && (
        <DataCard title={t('Все шаблоны школы')} note={t('Неиспользуемые в план не попадают')}>
          <DataTable columns={columns} rows={table} rowKey={(row) => row.id} flash={flashed} />
        </DataCard>
      )}

      {(adding || editing) && (
        <Modal
          title={editing ? t('Изменить шаблон') : t('Новый шаблон задачи')}
          note={t('Срок задаётся днём и месяцем — год подставится при генерации')}
          onClose={() => {
            setAdding(false)
            setEditing(null)
          }}
        >
          <RowForm
            fields={FIELDS}
            row={
              editing
                ? {
                    title: editing.title,
                    category: editing.category,
                    priority: editing.priority,
                    description: editing.description,
                    due_day: editing.due_day ?? '',
                    due_month: editing.due_month === null ? '' : String(editing.due_month),
                    grade: editing.grade ?? '',
                    graduation_year: editing.graduation_year ?? '',
                    is_active: editing.is_active,
                  }
                : { category: 'documents', priority: 'medium', is_active: true }
            }
            busy={rows.create.isPending || rows.update.isPending}
            submitLabel={editing ? t('Сохранить') : t('Завести')}
            onCancel={() => {
              setAdding(false)
              setEditing(null)
            }}
            onSubmit={(values) => {
              // сохранённая строка подсвечивается в списке: после закрытия
              // окна человек должен увидеть, куда легла его правка
              if (editing) {
                rows.update.mutate({ id: editing.id, ...body(values) })
                setFlashed(new Set([editing.id]))
              } else {
                rows.create.mutate(body(values), { onSuccess: (row) => setFlashed(new Set([row.id])) })
              }
              setAdding(false)
              setEditing(null)
            }}
          />
        </Modal>
      )}
    </div>
  )
}
