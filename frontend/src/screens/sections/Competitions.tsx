/**
 * Соревнования — экран директора спорта.
 *
 * До фазы 31 экран только показывал календарь: право заводить старты
 * у Нурлыбека было, а кнопки не было ни на одном экране. Теперь здесь
 * заводят, правят и убирают, а список участников вносится сразу —
 * соревнование одно, а строк в базе столько, сколько выступало.
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useCompetitionRows,
  useCompetitions,
  useDirectoryEntries,
  useStudents,
  type CompetitionRow,
} from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import DeleteButton from '../../components/DeleteButton'
import Empty from '../../components/Empty'
import Modal from '../../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../../components/RowForm'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'

const LEVELS = [
  { value: 'school', title: 'Школьный' },
  { value: 'city', title: 'Городской' },
  { value: 'regional', title: 'Областной' },
  { value: 'national', title: 'Республиканский' },
  { value: 'international', title: 'Международный' },
]

export default function Competitions() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<CompetitionRow | null>(null)
  const [picked, setPicked] = useState<number[]>([])
  const [problem, setProblem] = useState<string | null>(null)

  const list = useCompetitions({ search })
  const students = useStudents({ page_size: 500 })
  const sports = useDirectoryEntries('sport-types')
  const rows = useCompetitionRows()

  const sportOptions = useMemo(
    () =>
      (sports.data?.results ?? [])
        .filter((row) => row.is_active)
        .map((row) => ({ value: String(row.id), title: row.name })),
    [sports.data],
  )

  const fields: FieldDef[] = [
    { name: 'name', label: 'Название соревнования', kind: 'text', required: true },
    { name: 'sport_type', label: 'Вид спорта', kind: 'select', options: sportOptions },
    { name: 'level', label: 'Уровень', kind: 'select', options: LEVELS },
    { name: 'date', label: 'Дата', kind: 'date' },
    { name: 'result', label: 'Результат', kind: 'text' },
    { name: 'proof_url', label: 'Ссылка на подтверждение', kind: 'text' },
    { name: 'has_certificate', label: 'Есть сертификат', kind: 'checkbox' },
  ]

  const body = (values: RowValues) => ({
    name: String(values.name ?? ''),
    sport_type: values.sport_type ? Number(values.sport_type) : null,
    level: String(values.level ?? ''),
    date: values.date ? String(values.date) : null,
    result: String(values.result ?? ''),
    proof_url: String(values.proof_url ?? ''),
    has_certificate: Boolean(values.has_certificate),
  })

  const table = list.data?.results ?? []

  const columns: Column<CompetitionRow>[] = [
    {
      key: 'name',
      title: t('Соревнование'),
      width: '26%',
      cell: (row) => <b>{row.name}</b>,
    },
    {
      key: 'student',
      title: t('Участник'),
      width: '20%',
      cell: (row) => (
        <button className="cell cell-link" onClick={() => navigate(`/students/${row.student}`)}>
          {row.student_name}
        </button>
      ),
    },
    { key: 'sport', title: t('Вид спорта'), width: '14%', cell: (row) => row.sport_type_name || '—' },
    { key: 'level', title: t('Уровень'), width: '13%', cell: (row) => row.level_title || '—' },
    {
      key: 'date',
      title: t('Дата'),
      width: '11%',
      align: 'right',
      cell: (row) => (row.date ? new Date(row.date).toLocaleDateString('ru') : '—'),
    },
    { key: 'result', title: t('Результат'), width: '11%', cell: (row) => row.result || '—' },
    {
      key: 'actions',
      title: '',
      width: '110px',
      align: 'right',
      cell: (row) => (
        <span className="rows__actions">
          <button className="btn btn-ghost btn-sm" onClick={() => setEditing(row)}>
            {t('Изменить')}
          </button>
          <DeleteButton
            model="students.Competition"
            id={row.id}
            path="/competitions/"
            invalidate={[['competitions'], ['student-rows'], ['dashboard']]}
          />
        </span>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead title={t('Соревнования')} subtitle={t('Кто где выступал и с каким результатом.')} />

      <div className="toolbar">
        <input
          className="input"
          placeholder={t('Поиск по названию или результату')}
          aria-label={t('Поиск по соревнованиям')}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="toolbar__spacer" />
        <span className="muted">
          {counted(list.data?.count ?? 0, ['выступление', 'выступления', 'выступлений'])}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/import')}>
          {t('Загрузить файлом')}
        </button>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => {
            setPicked([])
            setProblem(null)
            setAdding(true)
          }}
        >
          {t('Добавить соревнование')}
        </button>
      </div>

      {list.isLoading && <Loading />}
      {list.error && <ErrorNote error={list.error} />}

      {!list.isLoading && table.length === 0 && (
        <Empty
          title={search ? t('По этому поиску ничего нет') : t('Соревнований пока нет')}
          what={
            search
              ? t('Очистите поиск, чтобы увидеть все выступления.')
              : t('Заведите первое — руками или файлом.')
          }
          hint={t(
            'Соревнование вносится один раз, а участников отмечают списком: у каждого своя строка со своим результатом.',
          )}
          action={search ? t('Очистить поиск') : t('Добавить соревнование')}
          onAction={search ? () => setSearch('') : () => setAdding(true)}
        />
      )}

      {table.length > 0 && (
        <DataCard title={t('Все выступления школы')} note={t('Строка на каждого участника')}>
          <DataTable columns={columns} rows={table} rowKey={(row) => row.id} />
        </DataCard>
      )}

      {adding && (
        <Modal
          title={t('Новое соревнование')}
          note={t('Отметьте всех, кто выступал — на каждого появится своя строка')}
          onClose={() => setAdding(false)}
        >
          <label className="rows__picker">
            <span className="rowform__label">{t('Участники')}</span>
            <div className="pickers">
              {(students.data?.results ?? []).map((row) => (
                <label key={row.id} className="pickers__item">
                  <input
                    type="checkbox"
                    checked={picked.includes(row.id)}
                    onChange={(event) =>
                      setPicked((prev) =>
                        event.target.checked ? [...prev, row.id] : prev.filter((id) => id !== row.id),
                      )
                    }
                  />
                  <span>{row.full_name}</span>
                </label>
              ))}
            </div>
          </label>
          {problem && <p className="chip chip-risk">{problem}</p>}
          <RowForm
            fields={fields}
            busy={rows.create.isPending}
            submitLabel={t('Завести')}
            onCancel={() => setAdding(false)}
            onSubmit={(values) => {
              if (picked.length === 0) {
                setProblem('Отметьте хотя бы одного участника — соревнование без выступавших не нужно')
                return
              }
              setProblem(null)
              const shared = body(values)
              picked.forEach((student) => rows.create.mutate({ student, ...shared }))
              setAdding(false)
            }}
          />
        </Modal>
      )}

      {editing && (
        <Modal title={t('Изменить выступление')} note={editing.student_name} onClose={() => setEditing(null)}>
          <RowForm
            fields={fields}
            row={{
              name: editing.name,
              sport_type: editing.sport_type === null ? '' : String(editing.sport_type),
              level: editing.level,
              date: editing.date ?? '',
              result: editing.result,
              proof_url: editing.proof_url,
              has_certificate: editing.has_certificate,
            }}
            busy={rows.update.isPending}
            submitLabel={t('Сохранить')}
            onCancel={() => setEditing(null)}
            onSubmit={(values) => {
              rows.update.mutate({ id: editing.id, ...body(values) })
              setEditing(null)
            }}
          />
        </Modal>
      )}
    </div>
  )
}
