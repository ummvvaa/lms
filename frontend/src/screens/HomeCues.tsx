/**
 * Сюжеты главной — настройка школы, ведёт администратор.
 *
 * Подсказки «Что закрыть» на главной ученика — не украшение, а список
 * незакрытых мест. Что считать незакрытым, решает условие из закрытого
 * набора; заголовок, описание и подпись кнопки ведёт школа — новый сюжет
 * заводится строкой, без выката. Надпись над заголовком собирает сервер:
 * в ней живое число, и в справочнике ему взяться неоткуда.
 *
 * Вид — по макету: таблица на две трети (номер, заголовок, условие,
 * кнопка, порядок стрелками, показывать), справа — первый включённый
 * сюжет так, как его увидит ученик. Числового «порядка» в форме нет:
 * новый сюжет встаёт последним, дальше его двигают. Правка — в правой панели.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useHomeCueDirectory, type HomeCueDirectoryRow } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { Switch } from '../components/ui/switch'
import { t } from '../i18n'
import Icon from '../layout/icons'
import './home-cues.css'

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
      width: '36%',
      cell: (row) => (
        // описание — по наведению: в строке, как в макете, только заголовок; целиком оно в превью и в правке
        <span className="cues__title" title={row.description || undefined}>
          <b>{row.title}</b>
        </span>
      ),
    },
    { key: 'condition', title: t('Показывается, когда'), width: '34%', cell: (row) => <span className="t-note cues__when">{row.condition_title}</span> },
    {
      key: 'action',
      title: t('Кнопка'),
      width: '30%',
      cell: (row) => (
        <span className="cues__action" title={row.action_path}>
          <Chip size="sm">
            <span className="cues__chiptext">{row.action_label}</span>
          </Chip>
        </span>
      ),
    },
    {
      // порядок стрелками, «показывать» и меню — одной линией справа, как в макете;
      // на телефоне — внизу карточки строки
      key: 'controls',
      title: '',
      width: '192px',
      actions: true,
      cell: (row) => {
        const index = rows.findIndex((item) => item.id === row.id)
        return (
          <span className="cues__controls">
            <Button variant="ghost" size="icon-sm" disabled={index === 0 || update.isPending} aria-label={`${t('Выше')}: ${row.title}`} onClick={() => move(index, -1)}>
              <Icon name="chevronUp" size={14} />
            </Button>
            <Button variant="ghost" size="icon-sm" disabled={index === rows.length - 1 || update.isPending} aria-label={`${t('Ниже')}: ${row.title}`} onClick={() => move(index, 1)}>
              <Icon name="chevronDown" size={14} />
            </Button>
            <Switch
              checked={row.is_active}
              aria-label={`${t('Показывать сюжет')}: ${row.title}`}
              disabled={update.isPending}
              onCheckedChange={(next) => update.mutate({ id: row.id, is_active: next }, { onError: fail })}
            />
            <RowMenu>
              <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
              <RowMenuItem risk onClick={() => remove.mutate(row.id, { onError: fail })}>
                {t('Удалить')}
              </RowMenuItem>
            </RowMenu>
          </span>
        )
      },
    },
  ]

  // первый включённый сюжет — тот, что ученик увидит первым, если условие выполнено
  const first = rows.find((row) => row.is_active)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Сюжеты главной')}
        subtitle={t('Подсказки «Что закрыть» на главной ученика')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить сюжет')}</Button>}
      />

      <div className="lay-3">
        <DataCard
          className="lay-span2"
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

        <DataCard className="card--beam" title={t('Так увидит ученик')}>
          <div className="cues__preview">
            {first ? (
              <div className="cues__hero">
                <span className="cues__eyebrow">{t('Что закрыть')}</span>
                <span className="cues__herotitle">{first.title}</span>
                {first.description && <span className="cues__herotext">{first.description}</span>}
                <span className="cues__herobtn">{first.action_label}</span>
              </div>
            ) : (
              <p className="t-note">{t('Включённых сюжетов нет — на главной ученика подсказок не будет')}</p>
            )}
            <p className="t-note">{t('Порядок решает, какой сюжет ученик увидит первым. Выключенные не показываются никому')}</p>
          </div>
        </DataCard>
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
