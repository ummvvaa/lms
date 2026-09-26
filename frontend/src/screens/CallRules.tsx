/**
 * Правила обзвона у директора школы.
 *
 * Из них собирается список «Кому позвонить сегодня»: условие из закрытого
 * набора, порог и формулировка причины. «Три пропуска подряд» и «пять» —
 * решение школы, а не программиста, и меняется оно здесь. Строки таблицей,
 * правка — в правой панели.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCallRuleDirectory, type CallRuleRow } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './academics/academics.css'

const FIELDS: FieldDef[] = [
  { name: 'code', label: t('Код правила'), kind: 'text', required: true, placeholder: 'attendance' },
  {
    name: 'condition',
    label: t('Условие'),
    kind: 'select',
    required: true,
    options: [
      { value: 'absences', title: t('Пропуски занятий') },
      { value: 'mock_drop', title: t('Просел по пробным') },
      { value: 'inactive', title: t('Не заходил в систему') },
      { value: 'missed_deadline', title: t('Пропустил дедлайн') },
      { value: 'no_contact', title: t('Нет контактов родителей') },
    ],
  },
  { name: 'reason', label: t('Причина одной фразой'), kind: 'text', required: true },
  {
    name: 'urgency',
    label: t('Срочность'),
    kind: 'select',
    required: true,
    options: [
      { value: 'now', title: t('Срочно') },
      { value: 'today', title: t('Сегодня') },
      { value: 'week', title: t('На неделе') },
    ],
  },
  { name: 'threshold', label: t('Порог: процент, дни или баллы'), kind: 'number' },
  { name: 'order', label: t('Порядок'), kind: 'number' },
  { name: 'is_active', label: t('Правило работает'), kind: 'checkbox' },
]

const URGENCY_TONE: Record<string, Tone> = { now: 'bad', today: 'warn', week: 'neutral' }

function payload(values: RowValues): Record<string, unknown> {
  return { ...values, threshold: values.threshold ?? 1, order: values.order ?? 100 }
}

export default function CallRules() {
  const { query, create, update, remove } = useCallRuleDirectory()
  const [editing, setEditing] = useState<CallRuleRow | null>(null)
  const [creating, setCreating] = useState(false)

  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />

  const rows = query.data?.results ?? []
  const fail = (error: Error) => toast.error(error.message)

  const columns: Column<CallRuleRow>[] = [
    { key: 'reason', title: t('Причина'), width: '34%', cell: (row) => <b>{row.reason}</b>, sortBy: (row) => row.reason.toLowerCase() },
    { key: 'condition', title: t('Условие'), width: '22%', cell: (row) => row.condition_title, sortBy: (row) => row.condition },
    { key: 'threshold', title: t('Порог'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.threshold}</span>, sortBy: (row) => row.threshold },
    {
      key: 'urgency',
      title: t('Срочность'),
      width: '14%',
      cell: (row) => (
        <Chip tone={URGENCY_TONE[row.urgency] ?? 'neutral'} size="sm">
          {row.urgency_title}
        </Chip>
      ),
      sortBy: (row) => row.urgency,
    },
    {
      key: 'active',
      title: t('Работает'),
      width: '12%',
      cell: (row) => (row.is_active ? <Chip tone="good" size="sm">{t('да')}</Chip> : <Chip size="sm">{t('выключено')}</Chip>),
      sortBy: (row) => (row.is_active ? 0 : 1),
    },
    {
      key: 'actions',
      title: '',
      width: '8%',
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
        title={t('Правила обзвона')}
        subtitle={t('Из них собирается список «Кому позвонить сегодня» на вашем дашборде.')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить правило')}</Button>}
      />

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Правила')}
            count={rows.length || undefined}
            empty={rows.length === 0 && t('заведите правило — по нему соберётся список тех, кому стоит позвонить')}
            emptyAction={
              <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
                {t('Добавить правило')}
              </Button>
            }
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={setEditing} selected={(row) => row.id === editing?.id} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <NoteCard title={t('Как читается порог')}>{t('Порог читается по условию: проценты у посещаемости, дни у входа, баллы у пробных. Список собирается из пропусков, моков, активности и дедлайнов.')}</NoteCard>
        </div>
      </div>

      <EditDrawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        title={editing ? editing.reason : t('Новое правило')}
        sub={t('Список собирается из пропусков, моков, активности и дедлайнов')}
      >
        <RowForm
          key={editing?.id ?? 'new'}
          fields={FIELDS}
          row={
            editing
              ? {
                  code: editing.code,
                  condition: editing.condition,
                  reason: editing.reason,
                  urgency: editing.urgency,
                  threshold: editing.threshold,
                  order: editing.order,
                  is_active: editing.is_active,
                }
              : { condition: 'absences', urgency: 'today', is_active: true, threshold: 1, order: 100 }
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
