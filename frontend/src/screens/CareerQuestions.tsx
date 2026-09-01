/**
 * Анкета профтеста у директора школы (фаза 45).
 *
 * Вопросы — справочник домена «Профиль и дисциплина», а не константы
 * в коде: школа меняет формулировки и добавляет свои, и новая анкета
 * не должна означать выкат.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerQuestions, type CareerQuestionRow } from '../api/hooks'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import './career.css'
import { t } from '../i18n'

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
      // с фазы 48 анкета отвечается нажатиями: «несколько вариантов» —
      // основной вид, свободный ответ остаётся полем «свой вариант»
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

  return (
    <div>
      <ScreenHead
        title={t('Вопросы профтеста')}
        subtitle={t(
          'Анкета, по которой ученик получает разбор направлений. Формулировки ведёте вы, а не код.',
        )}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить вопрос')}</Button>}
      />

      {rows.length > 0 && (
        <div className="card card-pad">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Вопрос')}</th>
                <th>{t('Вид ответа')}</th>
                <th>{t('Порядок')}</th>
                <th>{t('В анкете')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <b>{row.text}</b>
                    {row.hint && <div className="muted">{row.hint}</div>}
                  </td>
                  <td>{t(KIND_TITLE[row.kind] ?? 'Свободный ответ')}</td>
                  <td className="num">{row.order}</td>
                  <td>
                    {row.is_active ? (
                      <Badge variant="ok">{t('да')}</Badge>
                    ) : (
                      <Badge variant="mute">{t('скрыт')}</Badge>
                    )}
                  </td>
                  <td className="schol__rowactions">
                    <RowMenu>
                      <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
                      <RowMenuItem
                        risk
                        onClick={() =>
                          remove.mutate(row.id, { onError: (error) => toast.error(error.message) })
                        }
                      >
                        {t('Удалить')}
                      </RowMenuItem>
                    </RowMenu>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rows.length === 0 && (
        <Empty
          icon="bulb"
          title={t('Анкета пуста')}
          what={t('Заведите вопросы — по ним ученик получит разбор направлений.')}
          hint={t('Вопрос, на который уже отвечали, не удаляется: снимите галочку «Показывать в анкете».')}
          action={t('Добавить вопрос')}
          onAction={() => setCreating(true)}
        />
      )}

      {creating && (
        <Modal
          title={t('Новый вопрос')}
          note={t('Код нужен, чтобы ответы не перепутались')}
          onClose={() => setCreating(false)}
        >
          <RowForm
            fields={FIELDS}
            busy={create.isPending}
            submitLabel={t('Завести')}
            onCancel={() => setCreating(false)}
            onSubmit={(values) =>
              create.mutate(payload(values), {
                onSuccess: () => setCreating(false),
                onError: (error) => toast.error(error.message),
              })
            }
          />
        </Modal>
      )}

      {editing && (
        <Modal title={editing.text} onClose={() => setEditing(null)}>
          <RowForm
            fields={FIELDS}
            row={{
              code: editing.code,
              text: editing.text,
              hint: editing.hint,
              kind: editing.kind,
              options: editing.options,
              order: editing.order,
              is_active: editing.is_active,
            }}
            busy={update.isPending}
            submitLabel={t('Сохранить')}
            onCancel={() => setEditing(null)}
            onSubmit={(values) =>
              update.mutate(
                { id: editing.id, ...payload(values) },
                { onSuccess: () => setEditing(null), onError: (error) => toast.error(error.message) },
              )
            }
          />
        </Modal>
      )}
    </div>
  )
}
