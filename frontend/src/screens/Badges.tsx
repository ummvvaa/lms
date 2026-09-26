/**
 * Справочник бейджей у директора школы.
 *
 * Условие бейджа — строка справочника: мера плюс порог. Новый бейдж
 * заводится без выката, но мера берётся из закрытого набора — за балл
 * экзамена, GPA или статус бейджа быть не может (инвариант №12).
 *
 * Вид — таблица строками: название и подпись как увидит ученик, мера,
 * порог, переключатель «показывать»; правка — в правой панели.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useBadgeDirectory, type BadgeDirectoryRow } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { Switch } from '../components/ui/switch'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './academics/academics.css'

/** Меры, которые система умеет считать. Ни одной про баллы — инвариант №12. */
const METRICS = [
  { value: 'tasks_done', title: t('Выполненные задачи роадмапа') },
  { value: 'exercises_solved', title: t('Решённые упражнения') },
  { value: 'mocks_taken', title: t('Пройденные пробные экзамены') },
  { value: 'profile_sections', title: t('Заполненные разделы профиля') },
  { value: 'essays_started', title: t('Начатые эссе') },
  { value: 'onboarding_done', title: t('Пройденная анкета первого входа') },
  { value: 'materials_approved', title: t('Материалы, прошедшие проверку') },
  { value: 'resources_read', title: t('Прочитанные материалы раздела «Ресурсы»') },
  { value: 'streak_days', title: t('Дней подряд с действиями') },
  { value: 'plans_created', title: t('Созданные планы по вузам') },
  { value: 'quiz_matches', title: t('Сыгранные матчи квиза') },
  { value: 'documents_uploaded', title: t('Загруженные документы портфолио') },
]

const FIELDS: FieldDef[] = [
  { name: 'code', label: t('Код бейджа'), kind: 'text', required: true, placeholder: 'first_plan' },
  { name: 'name', label: t('Название бейджа'), kind: 'text', required: true },
  { name: 'description', label: t('Описание бейджа'), kind: 'text' },
  { name: 'metric', label: t('Что считает бейдж'), kind: 'select', required: true, options: METRICS },
  { name: 'threshold', label: t('Сколько нужно'), kind: 'number', required: true },
  { name: 'icon', label: t('Иконка'), kind: 'text', placeholder: 'medal' },
  { name: 'order', label: t('Порядок'), kind: 'number' },
  { name: 'is_active', label: t('Показывать бейдж'), kind: 'checkbox' },
]

function payload(values: RowValues): Record<string, unknown> {
  return {
    ...values,
    description: values.description ?? '',
    icon: values.icon || 'medal',
    threshold: values.threshold ?? 1,
    order: values.order ?? 100,
  }
}

export default function Badges() {
  const { query, create, update, remove } = useBadgeDirectory()
  const [editing, setEditing] = useState<BadgeDirectoryRow | null>(null)
  const [creating, setCreating] = useState(false)

  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />

  const rows = query.data?.results ?? []
  const fail = (error: Error) => toast.error(error.message)

  const columns: Column<BadgeDirectoryRow>[] = [
    {
      key: 'name',
      title: t('Бейдж'),
      width: '34%',
      cell: (row) => (
        <>
          <b>{row.name}</b>
          {row.description && <span className="t-note"> · {row.description}</span>}
        </>
      ),
      sortBy: (row) => row.name.toLowerCase(),
    },
    { key: 'metric', title: t('Даётся за'), width: '30%', cell: (row) => row.metric_title, sortBy: (row) => row.metric_title },
    { key: 'threshold', title: t('Нужно'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.threshold}</span>, sortBy: (row) => row.threshold },
    { key: 'order', title: t('Порядок'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.order}</span>, sortBy: (row) => row.order },
    {
      key: 'shown',
      title: t('Показывать'),
      width: '10%',
      cell: (row) => (
        <Switch
          checked={row.is_active}
          aria-label={`${t('Показывать бейдж')}: ${row.name}`}
          disabled={update.isPending}
          onCheckedChange={(next) => update.mutate({ id: row.id, is_active: next }, { onError: fail })}
        />
      ),
      sortBy: (row) => (row.is_active ? 0 : 1),
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
        title={t('Достижения школы')}
        subtitle={t('Условие бейджа — мера и порог. За баллы экзаменов бейджей не бывает: этого нет в списке мер.')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить бейдж')}</Button>}
      />

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Бейджи')}
            count={rows.length || undefined}
            empty={rows.length === 0 && t('заведите первый бейдж — ученики увидят его на экране достижений')}
            emptyAction={
              <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
                {t('Добавить бейдж')}
              </Button>
            }
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={setEditing} selected={(row) => row.id === editing?.id} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <NoteCard title={t('Как это работает')}>{t('Мера берётся из закрытого набора действий: за балл IELTS или GPA бейдж завести нельзя. Порог правится в строке, новый бейдж заводится без выката. Рейтингов и сравнения с другими учениками у ученика нет.')}</NoteCard>
        </div>
      </div>

      <EditDrawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        title={editing ? editing.name : t('Новый бейдж')}
        sub={t('Мера и порог: «решено 100 заданий», «7 дней подряд»')}
      >
        <RowForm
          key={editing?.id ?? 'new'}
          fields={FIELDS}
          row={
            editing
              ? {
                  code: editing.code,
                  name: editing.name,
                  description: editing.description,
                  metric: editing.metric,
                  threshold: editing.threshold,
                  icon: editing.icon,
                  order: editing.order,
                  is_active: editing.is_active,
                }
              : { is_active: true, threshold: 1, order: 100, icon: 'medal' }
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
              : create.mutate(payload(values), { onSuccess: () => setCreating(false), onError: fail })
          }
        />
      </EditDrawer>
    </div>
  )
}
