/**
 * Сюжеты главной — настройка школы, ведёт администратор.
 *
 * Подсказки «Что закрыть» на главной ученика — не украшение, а список
 * незакрытых мест. Что считать незакрытым, решает условие из закрытого
 * набора; заголовок, описание и подпись кнопки ведёт школа — новый сюжет
 * заводится строкой, без выката. Надпись над заголовком собирает сервер:
 * в ней живое число, и в справочнике ему взяться неоткуда.
 *
 * Вид — таблица: заголовок, условие, кнопка, показывать; порядок —
 * кнопками «выше» и «ниже» в строке. Числового «порядка» в форме нет:
 * новый сюжет встаёт последним, дальше его двигают. Правка — в правой панели.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useHomeCueDirectory, type HomeCueDirectoryRow } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { Switch } from '../components/ui/switch'
import { t } from '../i18n'
import './academics/academics.css'

/** Поля формы — функцией: подписи переводятся при показе, на языке человека. */
const fields = (): FieldDef[] => [
  { name: 'code', label: t('Код сюжета'), kind: 'text', required: true, placeholder: 'portfolio' },
  {
    name: 'condition',
    label: t('Условие показа'),
    kind: 'select',
    required: true,
    options: [
      { value: 'portfolio_gap', title: t('Портфолио заполнено не до конца') },
      { value: 'exam_goal_gap', title: t('До цели по экзамену не хватает') },
      { value: 'scholarship_deadline', title: t('Стипендии с ближайшим дедлайном не просмотрены') },
      { value: 'plan_idle', title: t('План не открывали неделю') },
      { value: 'no_universities', title: t('Список вузов пуст') },
      { value: 'documents_missing', title: t('Документы не загружены') },
    ],
  },
  { name: 'title', label: t('Заголовок'), kind: 'text', required: true },
  { name: 'description', label: t('Описание'), kind: 'textarea' },
  { name: 'action_label', label: t('Подпись кнопки'), kind: 'text', required: true },
  { name: 'action_path', label: t('Куда ведёт кнопка'), kind: 'text', required: true, placeholder: '/my-data' },
  { name: 'is_active', label: t('Показывать сюжет'), kind: 'checkbox' },
]

function payload(values: RowValues): Record<string, unknown> {
  return { ...values, description: values.description ?? '' }
}

/** Шаг между соседями: после перестановки порядок пишется заново, 10, 20, 30… */
const STEP = 10

export default function HomeCues() {
  const { query, create, update, remove } = useHomeCueDirectory()
  const [editing, setEditing] = useState<HomeCueDirectoryRow | null>(null)
  const [creating, setCreating] = useState(false)

  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />

  const rows = [...(query.data?.results ?? [])].sort((a, b) => a.order - b.order || a.id - b.id)
  const fail = (error: Error) => toast.error(error.message)

  // перестановка: меняем соседей местами и пишем порядок заново
  // только тем, у кого он изменился, — обычно это две строки
  const move = (index: number, by: -1 | 1) => {
    const next = [...rows]
    const [moved] = next.splice(index, 1)
    next.splice(index + by, 0, moved)
    next.forEach((row, place) => {
      const order = (place + 1) * STEP
      if (row.order !== order) update.mutate({ id: row.id, order }, { onError: fail })
    })
  }

  const columns: Column<HomeCueDirectoryRow>[] = [
    {
      key: 'title',
      title: t('Сюжет'),
      width: '30%',
      cell: (row) => (
        <>
          <b>{row.title}</b>
          {row.description && <span className="t-note"> · {row.description}</span>}
        </>
      ),
    },
    { key: 'condition', title: t('Показывается, когда'), width: '26%', cell: (row) => row.condition_title },
    {
      key: 'action',
      title: t('Кнопка'),
      width: '18%',
      cell: (row) => (
        <>
          {row.action_label}
          <span className="t-note"> · {row.action_path}</span>
        </>
      ),
    },
    {
      key: 'order',
      title: t('Порядок'),
      width: '12%',
      cell: (row) => {
        const index = rows.findIndex((item) => item.id === row.id)
        return (
          <span className="acad__inline">
            <Button variant="ghost" size="sm" disabled={index === 0 || update.isPending} aria-label={`${t('Выше')}: ${row.title}`} onClick={() => move(index, -1)}>
              {t('Выше')}
            </Button>
            <Button variant="ghost" size="sm" disabled={index === rows.length - 1 || update.isPending} aria-label={`${t('Ниже')}: ${row.title}`} onClick={() => move(index, 1)}>
              {t('Ниже')}
            </Button>
          </span>
        )
      },
    },
    {
      key: 'shown',
      title: t('Показывать'),
      width: '8%',
      cell: (row) => (
        <Switch
          checked={row.is_active}
          aria-label={`${t('Показывать сюжет')}: ${row.title}`}
          disabled={update.isPending}
          onCheckedChange={(next) => update.mutate({ id: row.id, is_active: next }, { onError: fail })}
        />
      ),
    },
    {
      key: 'actions',
      title: '',
      width: '6%',
      align: 'right',
      cell: (row) => (
        <RowMenu>
          <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
          <RowMenuItem risk onClick={() => remove.mutate(row.id, { onError: fail })}>
            {t('Удалить')}
          </RowMenuItem>
        </RowMenu>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Сюжеты главной')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить сюжет')}</Button>}
      />

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Сюжеты')}
            count={rows.length || undefined}
            empty={rows.length === 0 && t('заведите сюжет — он появится на главной, когда у ученика будет что закрывать')}
            emptyAction={
              <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
                {t('Добавить сюжет')}
              </Button>
            }
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={setEditing} selected={(row) => row.id === editing?.id} />
          </DataCard>
        </div>
      </div>

      <EditDrawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        title={editing ? editing.title : t('Новый сюжет')}
        sub={t('Пока условие не выполнено, сюжет на главной не показывается')}
      >
        <RowForm
          key={editing?.id ?? 'new'}
          fields={fields()}
          row={
            editing
              ? {
                  code: editing.code,
                  condition: editing.condition,
                  title: editing.title,
                  description: editing.description,
                  action_label: editing.action_label,
                  action_path: editing.action_path,
                  is_active: editing.is_active,
                }
              : { condition: 'portfolio_gap', is_active: true }
          }
          busy={create.isPending || update.isPending}
          submitLabel={editing ? t('Сохранить') : t('Завести')}
          onCancel={() => {
            setCreating(false)
            setEditing(null)
          }}
          onSubmit={(values) =>
            editing
              ? update.mutate({ id: editing.id, ...payload(values) }, { onSuccess: () => setEditing(null), onError: fail })
              : // новый сюжет встаёт последним; дальше его двигают
                create.mutate({ ...payload(values), order: (rows.length + 1) * STEP }, { onSuccess: () => setCreating(false), onError: fail })
          }
        />
      </EditDrawer>
    </div>
  )
}
