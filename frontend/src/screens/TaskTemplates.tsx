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
import { useStudyGroups, useTaskTemplates, useTemplateRows, type TaskTemplate } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import DeleteButton from '../components/DeleteButton'
import EditDrawer from '../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t, tk } from '../i18n'
import { Button } from '../components/ui/button'
import RowMenu, { RowMenuItem, RowMenuSeparator } from '../components/RowMenu'
import { formatDayMonth, monthName } from '../lib/format'

const CATEGORIES = [
  { value: 'test', title: tk('Тест') },
  { value: 'essay', title: tk('Эссе') },
  { value: 'documents', title: tk('Документы') },
  { value: 'university', title: tk('Вузы') },
  { value: 'portfolio', title: tk('Портфолио') },
  { value: 'finance', title: tk('Финансы') },
]

const PRIORITIES = [
  { value: 'high', title: tk('Высокий') },
  { value: 'medium', title: tk('Средний') },
  { value: 'low', title: tk('Низкий') },
]

/** Подписи из таблиц модуля — на языке человека, при рендере. */
const translated = (options: { value: string; title: string }[]) => options.map((option) => ({ ...option, title: t(option.title) }))

const baseFields = (): FieldDef[] => [
  { name: 'title', label: t('Название задачи'), kind: 'text', required: true },
  { name: 'category', label: t('Категория'), kind: 'select', options: translated(CATEGORIES), required: true },
  { name: 'priority', label: t('Важность'), kind: 'select', options: translated(PRIORITIES), required: true },
  { name: 'due_day', label: t('Срок: день'), kind: 'number' },
  {
    name: 'due_month',
    label: t('Срок: месяц'),
    kind: 'select',
    options: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map((index) => ({ value: String(index + 1), title: monthName(index) })),
  },
  { name: 'description', label: t('Описание'), kind: 'textarea' },
  { name: 'is_active', label: t('Используется'), kind: 'checkbox' },
]

function due(row: TaskTemplate): string {
  if (!row.due_month) return t('без срока')
  return formatDayMonth(`2026-${String(row.due_month).padStart(2, '0')}-${String(row.due_day ?? 1).padStart(2, '0')}`)
}

export default function TaskTemplates() {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<TaskTemplate | null>(null)
  // строка, которую только что завели или поправили: подсветится и погаснет
  const [flashed, setFlashed] = useState<ReadonlySet<number>>(new Set())
  const list = useTaskTemplates()
  const rows = useTemplateRows()

  const groups = useStudyGroups()

  const table = list.data?.results ?? []

  // кому шаблон: группы галочками. Школа ведёт только выпускников — класса
  // и года выпуска в форме нет; ничего не отмечено — шаблон идёт всем
  const FIELDS: FieldDef[] = [
    ...baseFields().slice(0, 5),
    {
      name: 'groups',
      label: t('Кому: группы'),
      kind: 'checks',
      options: (groups.data?.results ?? [])
        .filter((group) => group.is_active)
        .map((group) => ({ value: String(group.id), title: group.code })),
      placeholder: t('Ничего не отмечено — шаблон идёт всем группам'),
    },
    ...baseFields().slice(5),
  ]

  const body = (values: RowValues) => ({
    title: String(values.title ?? ''),
    category: String(values.category ?? 'documents'),
    priority: String(values.priority ?? 'medium'),
    description: String(values.description ?? ''),
    due_day: values.due_day === null ? null : Number(values.due_day),
    due_month: values.due_month === null ? null : Number(values.due_month),
    groups: String(values.groups ?? '')
      .split(',')
      .filter(Boolean)
      .map(Number),
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
      cell: (row) => t(CATEGORIES.find((c) => c.value === row.category)?.title ?? row.category),
      sortBy: (row) => row.category,
    },
    {
      key: 'priority',
      title: t('Важность'),
      width: '12%',
      cell: (row) => t(PRIORITIES.find((p) => p.value === row.priority)?.title ?? row.priority),
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
      cell: (row) => row.group_codes.join(', ') || t('всем'),
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
        actions={<Button onClick={() => setAdding(true)}>{t('Завести шаблон')}</Button>}
      />

      {list.isLoading && <Loading kind="table" />}
      {list.error && <ErrorNote error={list.error} />}

      {!list.isLoading && (
        <DataCard
          title={t('Все шаблоны школы')}
          count={table.length || undefined}
          note={table.length > 0 ? t('Неиспользуемые в план не попадают') : undefined}
          empty={table.length === 0 && t('заведите первый — по нему план появится у всего потока')}
          emptyAction={
            <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
              {t('Завести шаблон')}
            </Button>
          }
        >
          <DataTable columns={columns} rows={table} rowKey={(row) => row.id} flash={flashed} />
        </DataCard>
      )}

      <EditDrawer
        open={adding || editing !== null}
        onClose={() => {
          setAdding(false)
          setEditing(null)
        }}
        title={editing ? t('Изменить шаблон') : t('Новый шаблон задачи')}
        sub={t('Срок задаётся днём и месяцем — год подставится при генерации')}
      >
        <RowForm
          key={editing?.id ?? 'new'}
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
                  groups: editing.groups.join(','),
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
            // панели человек должен увидеть, куда легла его правка
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
      </EditDrawer>
    </div>
  )
}
