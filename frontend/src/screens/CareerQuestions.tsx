/**
 * Анкета профтеста у директора школы.
 *
 * Вопросы — справочник домена «Профиль и дисциплина», а не константы
 * в коде: школа меняет формулировки и добавляет свои, и новая анкета
 * не должна означать выкат. Строки таблицей, правка — в правой панели.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerQuestions, type CareerQuestionRow } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './academics/academics.css'

const FIELDS: FieldDef[] = [
  { name: 'code', label: t('Код вопроса'), kind: 'text', required: true, placeholder: 'favourite_subjects' },
  { name: 'text', label: t('Текст вопроса'), kind: 'text', required: true },
  { name: 'hint', label: t('Подсказка'), kind: 'text' },
  {
    name: 'kind',
    label: t('Вид ответа'),
    kind: 'select',
    required: true,
    options: [
      // анкета отвечается нажатиями: «несколько вариантов» — основной вид,
      // свободный ответ остаётся полем «свой вариант»
      { value: 'multi', title: t('Несколько вариантов') },
      { value: 'choice', title: t('Выбор из вариантов') },
      { value: 'text', title: t('Свободный ответ') },
    ],
  },
  { name: 'options', label: t('Варианты — по одному в строке'), kind: 'textarea' },
  { name: 'order', label: t('Порядок'), kind: 'number' },
  { name: 'is_active', label: t('Показывать в анкете'), kind: 'checkbox' },
]

const KIND_TITLE: Record<string, string> = {
  text: 'Свободный ответ',
  choice: 'Выбор из вариантов',
  multi: 'Несколько вариантов',
}

function payload(values: RowValues): Record<string, unknown> {
  return {
    ...values,
    hint: values.hint ?? '',
    options: values.options ?? '',
    order: values.order ?? 100,
  }
}

export default function CareerQuestions() {
  const { query, create, update, remove } = useCareerQuestions()
  const [editing, setEditing] = useState<CareerQuestionRow | null>(null)
  const [creating, setCreating] = useState(false)

  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />

  const rows = query.data?.results ?? []
  const fail = (error: Error) => toast.error(error.message)

  const columns: Column<CareerQuestionRow>[] = [
    {
      key: 'text',
      title: t('Вопрос'),
      width: '46%',
      cell: (row) => (
        <>
          <b>{row.text}</b>
          {row.hint && <span className="t-note"> · {row.hint}</span>}
        </>
      ),
      sortBy: (row) => row.text.toLowerCase(),
    },
    { key: 'kind', title: t('Вид ответа'), width: '20%', cell: (row) => t(KIND_TITLE[row.kind] ?? 'Свободный ответ'), sortBy: (row) => row.kind },
    { key: 'order', title: t('Порядок'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.order}</span>, sortBy: (row) => row.order },
    {
      key: 'active',
      title: t('В анкете'),
      width: '16%',
      cell: (row) => (row.is_active ? <Chip tone="good" size="sm">{t('да')}</Chip> : <Chip size="sm">{t('скрыт')}</Chip>),
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
        title={t('Вопросы профтеста')}
        subtitle={t('Анкета, по которой ученик получает разбор направлений. Формулировки ведёте вы, а не код.')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить вопрос')}</Button>}
      />

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Вопросы анкеты')}
            count={rows.length || undefined}
            empty={rows.length === 0 && t('заведите вопросы — по ним ученик получит разбор направлений')}
            emptyAction={
              <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
                {t('Добавить вопрос')}
              </Button>
            }
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={setEditing} selected={(row) => row.id === editing?.id} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <NoteCard title={t('Что важно')}>{t('Вопрос, на который уже отвечали, не удаляется: снимите галочку «Показывать в анкете». Код нужен, чтобы ответы не перепутались при смене формулировки.')}</NoteCard>
        </div>
      </div>

      <EditDrawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        title={editing ? editing.text : t('Новый вопрос')}
        sub={t('Код нужен, чтобы ответы не перепутались')}
      >
        <RowForm
          key={editing?.id ?? 'new'}
          fields={FIELDS}
          row={
            editing
              ? {
                  code: editing.code,
                  text: editing.text,
                  hint: editing.hint,
                  kind: editing.kind,
                  options: editing.options,
                  order: editing.order,
                  is_active: editing.is_active,
                }
              : { kind: 'multi', is_active: true, order: 100 }
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
