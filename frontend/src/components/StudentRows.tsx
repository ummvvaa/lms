/**
 * Дочерние строки ученика на его карточке: вузы, попытки, активности,
 * соревнования, контакты родителей, задачи и эссе.
 *
 * Здесь их заводят, правят и убирают. Право на всё три действия — одно
 * и то же: владелец домена (инвариант №1). До фазы 30 половина таблиц
 * умела только показывать и удалять, а завести строку было нечем.
 */
import { useState, type ReactNode } from 'react'
import {
  type ParentContact,
} from '../api/hooks'
import DeleteButton from './DeleteButton'
import RowComments from './RowComments'
import RowForm, { type FieldDef, type RowValues } from './RowForm'
import { Chip, DataCard } from './ui'
import { t } from '../i18n'
import { Button } from './ui/button'
import RowMenu, { RowMenuItem, RowMenuSeparator } from './RowMenu'

/** Кто ведёт строки этой таблицы. Совпадает с реестром доменов. */
const OWNER: Record<string, string[]> = {
  'universities.StudentUniversity': ['director_admission'],
  'students.ExamAttempt': ['director_exam'],
  'students.Activity': ['director_talent'],
  'students.Competition': ['director_sport'],
  'students.ParentContact': ['director_behavior'],
  'roadmap.Task': [
    'director_behavior',
    'director_admission',
    'director_exam',
    'director_talent',
    'director_sport',
  ],
  'roadmap.Essay': [
    'director_behavior',
    'director_admission',
    'director_exam',
    'director_talent',
    'director_sport',
  ],
}

export const TIER_OPTIONS = [
  { value: 'reach', title: 'Reach — вуз мечты' },
  { value: 'target', title: 'Target — реалистичный' },
  { value: 'safety', title: 'Safety — запасной' },
]


export const EXAM_TYPES = ['IELTS', 'TOEFL', 'SAT', 'ACT'].map((value) => ({ value, title: value }))


/** Категории активности — те же, что в модели. */
export const ACTIVITY_CATEGORY = [
  { value: 'olympiad', title: 'Олимпиада' },
  { value: 'project', title: 'Проект' },
  { value: 'research', title: 'Исследование' },
  { value: 'startup', title: 'Стартап' },
  { value: 'leadership', title: 'Лидерство' },
  { value: 'volunteering', title: 'Волонтёрство' },
  { value: 'competition', title: 'Конкурс' },
  { value: 'award', title: 'Награда' },
]

export const RELATION_OPTIONS = [
  { value: 'mother', title: 'Мама' },
  { value: 'father', title: 'Папа' },
  { value: 'guardian', title: 'Опекун' },
  { value: 'grandparent', title: 'Бабушка или дедушка' },
  { value: 'relative', title: 'Другой родственник' },
  { value: 'other', title: 'Другое' },
]

export const CHANNEL_OPTIONS = [
  { value: 'phone', title: 'Звонок' },
  { value: 'whatsapp', title: 'WhatsApp' },
  { value: 'telegram', title: 'Telegram' },
  { value: 'email', title: 'Почта' },
]

/** Поля формы контакта родителя — их же использует отдельный список. */
export const CONTACT_FIELDS: FieldDef[] = [
  { name: 'full_name', label: 'ФИО', kind: 'text', required: true },
  { name: 'relation', label: 'Кем приходится', kind: 'select', options: RELATION_OPTIONS, required: true },
  { name: 'phone', label: 'Телефон', kind: 'text', placeholder: '+7 …' },
  { name: 'email', label: 'Почта', kind: 'text' },
  { name: 'preferred_channel', label: 'Как связываться', kind: 'select', options: CHANNEL_OPTIONS },
  { name: 'note', label: 'Примечание', kind: 'textarea' },
  { name: 'is_primary', label: 'Основной контакт', kind: 'checkbox' },
]






export interface Row {
  id: number
  label: string
  note?: string
  /** значения для формы правки; пусто — строку правят на своём экране */
  values?: RowValues
  /** запись внёс куратор за ученика — подпись рядом со строкой */
  byCurator?: boolean
  /** строку здесь не правят и не убирают: пробник из файла, решение директора */
  locked?: boolean
}

/**
 * Секция строк одной таблицы: список, «Добавить», «Изменить», «Убрать».
 *
 * Экспортируется: теми же формами куратор вносит данные за ученика своей
 * группы. Право у него приходит с сервера (`mayWrite`, `mayRemove`),
 * у директора считается по владельцу таблицы, как раньше.
 */
export function RowsSection({
  title,
  note,
  hint,
  model,
  path,
  role,
  rows,
  empty,
  fields,
  onCreate,
  onUpdate,
  busy,
  addLabel,
  elsewhere,
  comments,
  mayWrite,
  mayRemove,
  foreignNote,
  invalidate,
  extraActions,
}: {
  title: string
  note?: string
  hint?: string
  model: string
  path: string
  role: string
  rows: Row[]
  empty: string
  /** состав формы; без него строка только показывается и удаляется */
  fields?: FieldDef[]
  onCreate?: (values: RowValues) => void
  onUpdate?: (id: number, values: RowValues) => void
  busy?: boolean
  addLabel?: string
  /** где строка правится, если не здесь */
  elsewhere?: string
  /** вид обсуждения под строкой: задача или эссе */
  comments?: 'task' | 'essay'
  /** право с сервера; не задано — по владельцу таблицы */
  mayWrite?: boolean
  /** право убрать запись; не задано — то же, что `mayWrite` */
  mayRemove?: boolean
  /** подпись под списком, когда строки ведёт кто-то другой */
  foreignNote?: string
  /** какие запросы обновить после удаления, кроме общих */
  invalidate?: string[][]
  /** свои пункты меню строки — «Сделать приоритетным» у вуза */
  extraActions?: (row: Row) => ReactNode
}) {
  // администратор пишет во все домены (реестр, фаза 68) — каждая правка в журнале с пометкой
  const mine = mayWrite ?? (role === 'admin' || (OWNER[model] ?? []).includes(role))
  const removable = mayRemove ?? mine
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [talking, setTalking] = useState<number | null>(null)
  const canEdit = mine && fields !== undefined && onUpdate !== undefined
  const mayAdd = Boolean(mine && fields && onCreate)
  const addButton = mayAdd ? (
    <Button variant="outline" size="sm" onClick={() => setAdding(!adding)}>
      {adding ? t('Отмена') : (addLabel ?? t('Добавить'))}
    </Button>
  ) : undefined

  // Строк нет и форма закрыта — блок сворачивается в одну строку (П-2, фаза 81):
  // «название — чего нет · кто ведёт» и кнопка, если роль может внести сама (П-4).
  // Раньше здесь стояла карточка во весь рост с одной серой фразой внутри,
  // и шесть таких подряд превращали вкладку в кладбище
  if (rows.length === 0 && !adding)
    return (
      <DataCard
        title={title}
        empty={empty}
        emptyAction={
          <span className="datacard__emptyact">
            {note && <span className="muted emptynote__who">{note}</span>}
            {addButton}
          </span>
        }
      />
    )

  return (
    <DataCard title={title} note={note} hint={hint} count={rows.length} right={addButton}>
      {adding && fields && onCreate && (
        <RowForm
          fields={fields}
          busy={busy}
          submitLabel={t('Добавить')}
          onCancel={() => setAdding(false)}
          onSubmit={(values) => {
            onCreate(values)
            setAdding(false)
          }}
        />
      )}

      <ul className="rows__list">
        {rows.map((row) => (
          <li key={row.id} className="rows__item">
            <div className="rows__body">
              <div>
                <span className="rows__label">{row.label}</span>
                {row.note && <span className="muted rows__note"> · {row.note}</span>}
                {row.byCurator && (
                  <Chip tone="neutral" className="rows__by">
                    {t('внёс куратор')}
                  </Chip>
                )}
              </div>
              <div className="rows__actions">
                {/* обсуждение остаётся кнопкой: оно не действие над строкой,
                    а её вторая половина. Правка и удаление — в меню */}
                {comments && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setTalking(talking === row.id ? null : row.id)}
                  >
                    {talking === row.id ? t('Скрыть') : t('Обсуждение')}
                  </Button>
                )}
                {!row.locked && ((canEdit && row.values) || removable) && (
                  <RowMenu>
                    {canEdit && row.values && (
                      <RowMenuItem onClick={() => setEditing(editing === row.id ? null : row.id)}>
                        {editing === row.id ? t('Закрыть') : t('Изменить')}
                      </RowMenuItem>
                    )}
                    {mine && extraActions?.(row)}
                    {removable && canEdit && row.values && <RowMenuSeparator />}
                    {removable && (
                      <RowMenuItem risk keepOpen>
                        <DeleteButton
                          inMenu
                          model={model}
                          id={row.id}
                          path={path}
                          invalidate={[
                            ['student-rows'],
                            ['students'],
                            ['match'],
                            ['contacts'],
                            ...(invalidate ?? []),
                          ]}
                        />
                      </RowMenuItem>
                    )}
                  </RowMenu>
                )}
              </div>
            </div>
            {comments && talking === row.id && <RowComments kind={comments} id={row.id} />}
            {canEdit && editing === row.id && row.values && fields && (
              <RowForm
                fields={fields}
                row={row.values}
                busy={busy}
                submitLabel={t('Сохранить')}
                onCancel={() => setEditing(null)}
                onSubmit={(values) => {
                  onUpdate?.(row.id, values)
                  setEditing(null)
                }}
              />
            )}
          </li>
        ))}
      </ul>

      {!mine && rows.length > 0 && (
        <p className="muted rows__empty">{foreignNote ?? t('Эти строки ведёт другой директор')}</p>
      )}
      {mine && elsewhere && <p className="muted rows__empty">{elsewhere}</p>}
    </DataCard>
  )
}


export function contactRow(row: ParentContact): Row {
  return {
    id: row.id,
    label: row.full_name + (row.is_primary ? ' · основной' : ''),
    note: [row.relation_title, row.phone, row.email, row.channel_title].filter(Boolean).join(' · '),
    values: {
      full_name: row.full_name,
      relation: row.relation,
      phone: row.phone,
      email: row.email,
      preferred_channel: row.preferred_channel,
      note: row.note,
      is_primary: row.is_primary,
    },
  }
}

/** Тело запроса контакта: пустые поля уходят строкой, а не null. */
export function contactBody(values: RowValues) {
  return {
    full_name: String(values.full_name ?? ''),
    relation: String(values.relation ?? 'other'),
    phone: String(values.phone ?? ''),
    email: String(values.email ?? ''),
    preferred_channel: String(values.preferred_channel ?? ''),
    note: String(values.note ?? ''),
    is_primary: Boolean(values.is_primary),
  }
}
