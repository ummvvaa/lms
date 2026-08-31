/**
 * Справочник стипендий у директора по поступлению (фаза 44).
 *
 * Здесь их заводят руками, правят и убирают. Файлом стипендии грузит
 * администратор за домен «Поступление» (фаза 35) — на экране об этом
 * написано, чтобы Асем не искала кнопку загрузки.
 *
 * Правка руками снимает плашку «не подтверждено»: сверять записи по сайту —
 * её работа, и вторая кнопка после каждой правки означала бы справочник
 * в плашках навсегда (решение фазы 29).
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useDirectory,
  useScholarshipAttention,
  useScholarshipDirectory,
  useScholarships,
  type ScholarshipRow,
} from '../api/hooks'
import DeleteButton from '../components/DeleteButton'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import './scholarships.css'
import { t } from '../i18n'

type Mode = 'list' | 'students'

/** Состав формы. Подписи — те же слова, что в реестре полей на сервере. */
function fieldsOf(universities: { id: number; name: string }[]): FieldDef[] {
  return [
    { name: 'name', label: t('Название стипендии'), kind: 'text', required: true },
    { name: 'organizer', label: t('Организатор'), kind: 'text' },
    { name: 'country', label: t('Страна'), kind: 'text' },
    {
      name: 'level',
      label: t('Уровень обучения'),
      kind: 'select',
      options: [
        { value: 'bachelor', title: t('Бакалавриат') },
        { value: 'master', title: t('Магистратура') },
        { value: 'foundation', title: 'Foundation' },
      ],
    },
    {
      name: 'funding_type',
      label: t('Тип финансирования'),
      kind: 'select',
      required: true,
      options: [
        { value: 'full', title: t('Полное финансирование') },
        { value: 'partial', title: t('Частичное финансирование') },
        { value: 'tuition', title: t('Только обучение') },
      ],
    },
    { name: 'amount_min', label: t('Сумма от'), kind: 'number' },
    { name: 'amount_max', label: t('Сумма до'), kind: 'number' },
    { name: 'currency', label: t('Валюта'), kind: 'text', placeholder: 'USD' },
    { name: 'for_international', label: t('Для иностранцев'), kind: 'checkbox' },
    { name: 'for_merit', label: t('За заслуги'), kind: 'checkbox' },
    { name: 'for_need', label: t('По нужде'), kind: 'checkbox' },
    { name: 'deadline', label: t('Дедлайн подачи'), kind: 'date' },
    { name: 'url', label: t('Ссылка на страницу'), kind: 'text' },
    { name: 'requirements', label: t('Требования'), kind: 'textarea' },
    { name: 'description', label: t('Описание'), kind: 'textarea' },
    {
      name: 'university',
      label: t('Вуз стипендии'),
      kind: 'select',
      options: universities.map((row) => ({ value: String(row.id), title: row.name })),
    },
  ]
}

function valuesOf(row: ScholarshipRow): RowValues {
  return {
    name: row.name,
    organizer: row.organizer,
    country: row.country,
    level: row.level,
    funding_type: row.funding_type,
    amount_min: row.amount_min,
    amount_max: row.amount_max,
    currency: row.currency,
    for_international: row.for_international,
    for_merit: row.for_merit,
    for_need: row.for_need,
    deadline: row.deadline,
    url: row.url,
    requirements: row.requirements,
    description: row.description,
    university: row.university,
  }
}

/**
 * Пустая клетка формы — не `null` для всех подряд.
 *
 * `RowForm` отдаёт незаполненное как `null`, а текстовая колонка `null`
 * не принимает и отвечает четырёхсотой. Поэтому пустоту переводим
 * в собственную пустоту поля: тексту — пустая строка, числу, дате
 * и ссылке на вуз — `null` (тот же приём, что при снятии ответа анкеты).
 */
function toPayload(values: RowValues, fields: FieldDef[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  fields.forEach((field) => {
    const value = values[field.name]
    if (value !== null && value !== undefined && value !== '') {
      out[field.name] = value
      return
    }
    if (field.kind === 'checkbox') out[field.name] = Boolean(value)
    else if (field.kind === 'number' || field.kind === 'date' || field.name === 'university') {
      out[field.name] = null
    } else out[field.name] = ''
  })
  return out
}

export default function ScholarshipDirectory() {
  const [mode, setMode] = useState<Mode>('list')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<ScholarshipRow | null>(null)
  const [creating, setCreating] = useState(false)

  const list = useScholarships(search ? { q: search } : {})
  const universities = useDirectory()
  const attention = useScholarshipAttention(mode === 'students')
  const { create, update } = useScholarshipDirectory()

  const rows = list.data?.results ?? []
  const fields = fieldsOf((universities.data?.results ?? []).map((row) => ({ id: row.id, name: row.name })))

  return (
    <div>
      <ScreenHead
        title={t('Стипендии')}
        subtitle={t(
          'Справочник грантов и стипендий: его видит ученик в своём разделе. Файлом их грузит администратор.',
        )}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить стипендию')}</Button>}
      />

      <ScreenTabs
        value={mode}
        onChange={setMode}
        items={[
          { value: 'list', label: t('Справочник') },
          { value: 'students', label: t('Кто что сохранил') },
        ]}
      />

      {mode === 'list' && (
        <>
          <div className="toolbar">
            <Input
              placeholder={t('Название или организатор')}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <span className="toolbar__spacer" />
            <Badge variant="mute" className="num">
              {list.data?.count ?? 0}
            </Badge>
          </div>

          {list.isLoading && <Loading kind="table" />}
          {list.error && <ErrorNote error={list.error} />}

          {rows.length > 0 && (
            <div className="card card-pad schol__tablewrap">
              <table className="tbl schol__table">
                <thead>
                  <tr>
                    <th>{t('Стипендия')}</th>
                    <th>{t('Страна')}</th>
                    <th>{t('Финансирование')}</th>
                    <th>{t('Сумма')}</th>
                    <th>{t('Дедлайн')}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <b>{row.name}</b>
                        {row.organizer && <div className="muted">{row.organizer}</div>}
                        {!row.is_verified && (
                          <Badge variant="warn" className="badge--line">
                            {t('не подтверждено')}
                          </Badge>
                        )}
                      </td>
                      <td>{row.country || '—'}</td>
                      <td>{row.funding_title}</td>
                      <td className="num">{row.amount_title || '—'}</td>
                      <td>{row.deadline_state}</td>
                      <td className="schol__rowactions">
                        <RowMenu>
                          <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
                          <DeleteButton
                            model="universities.Scholarship"
                            id={row.id}
                            path="/scholarships/"
                            invalidate={[['scholarships'], ['scholarship-overview']]}
                            inMenu
                            onDeleted={(detail) => toast.success(detail)}
                          />
                        </RowMenu>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!list.isLoading && rows.length === 0 && (
            <Empty
              icon="card"
              title={search ? t('По этому запросу ничего нет') : t('Справочник стипендий пуст')}
              what={t('Заведите первую стипендию — ученики увидят её в своём разделе.')}
              hint={t(
                'Файл со списком стипендий загружает администратор: «Импорт» → домен «Поступление» → «Стипендии». Загруженные записи придут с плашкой «не подтверждено».',
              )}
              action={t('Добавить стипендию')}
              onAction={() => setCreating(true)}
            />
          )}
        </>
      )}

      {mode === 'students' && (
        <>
          {attention.isLoading && <Loading kind="cards" />}
          {attention.error && <ErrorNote error={attention.error} />}
          <div className="grid grid--two">
            <DataCard
              title={t('Дедлайн на этой неделе')}
              note={t('Успеть подать осталось несколько дней')}
              count={attention.data?.deadline_this_week.length ?? 0}
              accent="warn"
            >
              <ul className="rows__list">
                {(attention.data?.deadline_this_week ?? []).map((row) => (
                  <li key={row.student}>
                    <b>{row.student_name}</b>
                    <span className="muted">
                      {' '}
                      · {row.soon.map((item) => `${item.name} (${item.deadline_state})`).join(', ')}
                    </span>
                  </li>
                ))}
                {(attention.data?.deadline_this_week ?? []).length === 0 && (
                  <li className="muted">{t('Ни у кого дедлайна на неделе нет')}</li>
                )}
              </ul>
            </DataCard>

            <DataCard
              title={t('Сохранили стипендии')}
              note={t('Кто и сколько отметил себе')}
              count={attention.data?.saved_by.length ?? 0}
              accent="teal"
            >
              <ul className="rows__list">
                {(attention.data?.saved_by ?? []).map((row) => (
                  <li key={row.student}>
                    <b>{row.student_name}</b> <span className="muted num">· {row.saved}</span>
                  </li>
                ))}
                {(attention.data?.saved_by ?? []).length === 0 && (
                  <li className="muted">{t('Пока никто ничего не сохранил')}</li>
                )}
              </ul>
            </DataCard>

            <DataCard
              title={t('Не сохранил ни одной')}
              note={t('С ними стоит поговорить про финансирование')}
              count={attention.data?.without_saved.length ?? 0}
            >
              <ul className="rows__list">
                {(attention.data?.without_saved ?? []).map((row) => (
                  <li key={row.student}>{row.student_name}</li>
                ))}
                {(attention.data?.without_saved ?? []).length === 0 && (
                  <li className="muted">{t('Все что-то сохранили')}</li>
                )}
              </ul>
            </DataCard>
          </div>
        </>
      )}

      {creating && (
        <Modal
          title={t('Новая стипендия')}
          note={t('Обязательны название и тип финансирования')}
          onClose={() => setCreating(false)}
        >
          <RowForm
            fields={fields}
            busy={create.isPending}
            submitLabel={t('Завести')}
            onCancel={() => setCreating(false)}
            onSubmit={(values) =>
              create.mutate(toPayload(values, fields), {
                onSuccess: () => setCreating(false),
                onError: (error) => toast.error(error.message),
              })
            }
          />
        </Modal>
      )}

      {editing && (
        <Modal
          title={editing.name}
          note={t('Правка руками снимает плашку «не подтверждено»')}
          onClose={() => setEditing(null)}
        >
          <RowForm
            fields={fields}
            row={valuesOf(editing)}
            busy={update.isPending}
            submitLabel={t('Сохранить')}
            onCancel={() => setEditing(null)}
            onSubmit={(values) =>
              update.mutate(
                { id: editing.id, ...toPayload(values, fields) },
                {
                  onSuccess: () => setEditing(null),
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          />
        </Modal>
      )}
    </div>
  )
}
