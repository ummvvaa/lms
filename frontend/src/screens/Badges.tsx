/**
 * Справочник бейджей у директора школы (фаза 46).
 *
 * Условие бейджа — строка справочника: мера плюс порог. Новый бейдж
 * заводится без выката, но мера берётся из закрытого набора — за балл
 * экзамена, GPA или статус бейджа быть не может (инвариант №12).
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useBadgeDirectory, type BadgeDirectoryRow } from '../api/hooks'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { t } from '../i18n'

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

  return (
    <div>
      <ScreenHead
        title={t('Достижения школы')}
        subtitle={t(
          'Условие бейджа — мера и порог. За баллы экзаменов бейджей не бывает: этого нет в списке мер.',
        )}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить бейдж')}</Button>}
      />

      {rows.length > 0 && (
        <div className="card card-pad">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Бейдж')}</th>
                <th>{t('Что считает бейдж')}</th>
                <th>{t('Сколько нужно')}</th>
                <th>{t('Показывать бейдж')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <b>{row.name}</b>
                    {row.description && <div className="muted">{row.description}</div>}
                  </td>
                  <td>{row.metric_title}</td>
                  <td className="num">{row.threshold}</td>
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
          icon="medal"
          title={t('Бейджей нет')}
          what={t('Заведите первый бейдж — ученики увидят его на экране достижений.')}
          hint={t('Мера берётся из закрытого набора действий: за балл IELTS или GPA бейдж завести нельзя.')}
          action={t('Добавить бейдж')}
          onAction={() => setCreating(true)}
        />
      )}

      {creating && (
        <Modal
          title={t('Новый бейдж')}
          note={t('Мера и порог: «решено 100 заданий», «7 дней подряд»')}
          onClose={() => setCreating(false)}
        >
          <RowForm
            fields={FIELDS}
            row={{ is_active: true, threshold: 1, order: 100, icon: 'medal' }}
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
        <Modal title={editing.name} onClose={() => setEditing(null)}>
          <RowForm
            fields={FIELDS}
            row={{
              code: editing.code,
              name: editing.name,
              description: editing.description,
              metric: editing.metric,
              threshold: editing.threshold,
              icon: editing.icon,
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
