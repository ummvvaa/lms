/**
 * Правила обзвона у директора школы (фаза 49).
 *
 * Из них собирается список «Кому позвонить сегодня»: условие из закрытого
 * набора, порог и формулировка причины. «Три пропуска подряд» и «пять» —
 * решение школы, а не программиста, и меняется оно здесь.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCallRuleDirectory, type CallRuleRow } from '../api/hooks'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge, type BadgeVariant } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { t } from '../i18n'

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

const URGENCY_TONE: Record<string, BadgeVariant> = { now: 'risk', today: 'warn', week: 'mute' }

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

  return (
    <div>
      <ScreenHead
        title={t('Правила обзвона')}
        subtitle={t('Из них собирается список «Кому позвонить сегодня» на вашем дашборде.')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить правило')}</Button>}
      />

      {rows.length > 0 && (
        <div className="card card-pad">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Причина')}</th>
                <th>{t('Условие')}</th>
                <th>{t('Порог')}</th>
                <th>{t('Срочность')}</th>
                <th>{t('Работает')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <b>{row.reason}</b>
                  </td>
                  <td>{row.condition_title}</td>
                  <td className="num">{row.threshold}</td>
                  <td>
                    <Badge variant={URGENCY_TONE[row.urgency] ?? 'mute'}>{row.urgency_title}</Badge>
                  </td>
                  <td>
                    {row.is_active ? (
                      <Badge variant="ok">{t('да')}</Badge>
                    ) : (
                      <Badge variant="mute">{t('выключено')}</Badge>
                    )}
                  </td>
                  <td>
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
          icon="person"
          title={t('Правил обзвона нет')}
          what={t('Заведите правило — по нему соберётся список тех, кому стоит позвонить.')}
          hint={t('Порог читается по условию: проценты у посещаемости, дни у входа, баллы у пробных.')}
          action={t('Добавить правило')}
          onAction={() => setCreating(true)}
        />
      )}

      {creating && (
        <Modal
          title={t('Новое правило')}
          note={t('Список собирается из пропусков, моков, активности и дедлайнов')}
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
        <Modal title={editing.reason} onClose={() => setEditing(null)}>
          <RowForm
            fields={FIELDS}
            row={{
              code: editing.code,
              condition: editing.condition,
              reason: editing.reason,
              urgency: editing.urgency,
              threshold: editing.threshold,
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
