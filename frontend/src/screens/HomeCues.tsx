/**
 * Сюжеты главной у директора школы (фаза 49).
 *
 * Карусель на главной ученика — не украшение, а список незакрытых мест.
 * Что считать незакрытым, решает условие из закрытого набора; заголовок,
 * описание, подпись кнопки и цвет ведёт школа — новый сюжет заводится
 * строкой, без выката. Надпись над заголовком собирает сервер: в ней
 * живое число, и в справочнике ему взяться неоткуда.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useHomeCueDirectory, type HomeCueDirectoryRow } from '../api/hooks'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { t } from '../i18n'

const FIELDS: FieldDef[] = [
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
  {
    name: 'action_path',
    label: t('Куда ведёт кнопка'),
    kind: 'text',
    required: true,
    placeholder: '/my-data',
  },
  {
    name: 'tone',
    label: t('Цвет карточки'),
    kind: 'select',
    required: true,
    options: [
      { value: 'brand', title: t('Оранжевый') },
      { value: 'ink', title: t('Графит') },
      { value: 'teal', title: t('Бирюза') },
      { value: 'indigo', title: t('Индиго') },
    ],
  },
  { name: 'order', label: t('Порядок'), kind: 'number' },
  { name: 'is_active', label: t('Показывать сюжет'), kind: 'checkbox' },
]

function payload(values: RowValues): Record<string, unknown> {
  return { ...values, description: values.description ?? '', order: values.order ?? 100 }
}

export default function HomeCues() {
  const { query, create, update, remove } = useHomeCueDirectory()
  const [editing, setEditing] = useState<HomeCueDirectoryRow | null>(null)
  const [creating, setCreating] = useState(false)

  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />

  const rows = query.data?.results ?? []

  return (
    <div>
      <ScreenHead
        title={t('Сюжеты главной')}
        subtitle={t('Карусель на главной ученика: по одному сюжету на каждое незакрытое место.')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить сюжет')}</Button>}
      />

      {rows.length > 0 && (
        <div className="card card-pad">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Заголовок')}</th>
                <th>{t('Условие')}</th>
                <th>{t('Кнопка')}</th>
                <th>{t('Порядок')}</th>
                <th>{t('Показывать')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <b>{row.title}</b>
                    {row.description && <div className="muted">{row.description}</div>}
                  </td>
                  <td>{row.condition_title}</td>
                  <td>
                    {row.action_label} → {row.action_path}
                  </td>
                  <td className="num">{row.order}</td>
                  <td>
                    {row.is_active ? (
                      <Badge variant="ok">{t('да')}</Badge>
                    ) : (
                      <Badge variant="mute">{t('скрыт')}</Badge>
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
          icon="bulb"
          title={t('Сюжетов пока нет')}
          what={t('Заведите сюжет — он появится на главной, когда у ученика будет что закрывать.')}
          hint={t('Условие берётся из закрытого набора: считать его должен код, а не текст.')}
          action={t('Добавить сюжет')}
          onAction={() => setCreating(true)}
        />
      )}

      {creating && (
        <Modal
          title={t('Новый сюжет')}
          note={t('Пока условие не выполнено, сюжет на главной не показывается')}
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
        <Modal title={editing.title} onClose={() => setEditing(null)}>
          <RowForm
            fields={FIELDS}
            row={{
              code: editing.code,
              condition: editing.condition,
              title: editing.title,
              description: editing.description,
              action_label: editing.action_label,
              action_path: editing.action_path,
              tone: editing.tone,
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
