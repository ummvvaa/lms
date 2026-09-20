/**
 * Сюжеты главной — настройка школы, ведёт администратор.
 *
 * Карусель на главной ученика — не украшение, а список незакрытых мест.
 * Что считать незакрытым, решает условие из закрытого набора; заголовок,
 * описание, подпись кнопки и цвет ведёт школа — новый сюжет заводится
 * строкой, без выката. Надпись над заголовком собирает сервер: в ней
 * живое число, и в справочнике ему взяться неоткуда.
 *
 * Вид — карточки, а не таблица: заголовок и подпись как увидит ученик,
 * ниже строкой «Показывается, когда: …» и «Ведёт на: …», переключатель
 * «показывать» справа, порядок — стрелками. Числового «порядка» в форме
 * нет: новый сюжет встаёт последним, дальше его двигают.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useHomeCueDirectory, type HomeCueDirectoryRow } from '../api/hooks'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import SettingCard from '../components/SettingCard'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
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

  // перестановка стрелкой: меняем соседей местами и пишем порядок заново
  // только тем, у кого он изменился, — обычно это две строки
  const move = (index: number, by: -1 | 1) => {
    const next = [...rows]
    const [moved] = next.splice(index, 1)
    next.splice(index + by, 0, moved)
    next.forEach((row, place) => {
      const order = (place + 1) * STEP
      if (row.order !== order)
        update.mutate({ id: row.id, order }, { onError: (error) => toast.error(error.message) })
    })
  }

  return (
    <div>
      <ScreenHead
        title={t('Сюжеты главной')}
        subtitle={t('Карусель на главной ученика: по одному сюжету на каждое незакрытое место.')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить сюжет')}</Button>}
      />

      {rows.length > 0 && (
        <div className="scards">
          {rows.map((row, index) => (
            <SettingCard
              key={row.id}
              title={row.title}
              subtitle={row.description || undefined}
              tone={row.tone}
              shown={row.is_active}
              busy={update.isPending}
              onShown={(next) =>
                update.mutate(
                  { id: row.id, is_active: next },
                  { onError: (error) => toast.error(error.message) },
                )
              }
              onUp={index > 0 ? () => move(index, -1) : undefined}
              onDown={index < rows.length - 1 ? () => move(index, 1) : undefined}
              facts={[
                { label: t('Показывается, когда:'), value: row.condition_title },
                { label: t('Ведёт на:'), value: `${row.action_label} → ${row.action_path}` },
              ]}
              menu={
                <RowMenu>
                  <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
                  <RowMenuItem
                    risk
                    onClick={() => remove.mutate(row.id, { onError: (error) => toast.error(error.message) })}
                  >
                    {t('Удалить')}
                  </RowMenuItem>
                </RowMenu>
              }
            />
          ))}
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
              // новый сюжет встаёт последним; дальше его двигают стрелками
              create.mutate(
                { ...payload(values), order: (rows.length + 1) * STEP },
                {
                  onSuccess: () => setCreating(false),
                  onError: (error) => toast.error(error.message),
                },
              )
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
