/**
 * Соревнования — экран директора спорта.
 *
 * До фазы 31 экран только показывал календарь: право заводить старты
 * у Нурлыбека было, а кнопки не было ни на одном экране. Теперь здесь
 * заводят, правят и убирают, а список участников вносится сразу —
 * соревнование одно, а строк в базе столько, сколько выступало.
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  useCompetitionRows,
  useCompetitions,
  useDirectoryEntries,
  useStudents,
  type CompetitionRow,
} from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import DeleteButton from '../../components/DeleteButton'
import ManualEntryNote from '../../components/ManualEntryNote'
import EditDrawer from '../../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../../components/RowForm'
import { Chip, counted, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t, tk } from '../../i18n'
import { Input } from '../../components/ui/input'
import { Checkbox } from '../../components/ui/checkbox'
import { Switch } from '../../components/ui/switch'
import { Button } from '../../components/ui/button'
import RowMenu, { RowMenuItem, RowMenuSeparator } from '../../components/RowMenu'
import { formatDate } from '../../lib/format'

/** Уровни соревнования — ключи перевода, в форму идут через `t()`. */
const LEVELS = [
  { value: 'school', title: tk('Школьный') },
  { value: 'city', title: tk('Городской') },
  { value: 'regional', title: tk('Областной') },
  { value: 'national', title: tk('Республиканский') },
  { value: 'international', title: tk('Международный') },
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
    { name: 'name', label: t('Название соревнования'), kind: 'text', required: true },
    { name: 'sport_type', label: t('Вид спорта'), kind: 'select', options: sportOptions },
    {
      name: 'level',
      label: t('Уровень'),
      kind: 'select',
      options: LEVELS.map((level) => ({ value: level.value, title: t(level.title) })),
    },
    { name: 'date', label: t('Дата'), kind: 'date' },
    { name: 'result', label: t('Результат'), kind: 'text' },
    { name: 'proof_url', label: t('Ссылка на подтверждение'), kind: 'text' },
    { name: 'has_certificate', label: t('Есть сертификат'), kind: 'checkbox' },
    { name: 'show_in_card', label: t('Показывать в карточке ученика'), kind: 'checkbox' },
  ]

  const body = (values: RowValues) => ({
    name: String(values.name ?? ''),
    sport_type: values.sport_type ? Number(values.sport_type) : null,
    level: String(values.level ?? ''),
    date: values.date ? String(values.date) : null,
    result: String(values.result ?? ''),
    proof_url: String(values.proof_url ?? ''),
    has_certificate: Boolean(values.has_certificate),
    show_in_card: Boolean(values.show_in_card),
  })

  const table = list.data?.results ?? []

  const columns: Column<CompetitionRow>[] = [
    {
      key: 'name',
      title: t('Соревнование'),
      width: '26%',
      cell: (row) => <b>{row.name}</b>,
      sortBy: (row) => row.name.toLowerCase(),
    },
    {
      key: 'student',
      title: t('Участник'),
      width: '20%',
      cell: (row) => (
        <Button variant="link" size="sm" onClick={() => navigate(`/students/${row.student}`)}>
          {row.student_name}
        </Button>
      ),
      sortBy: (row) => row.student_name.toLowerCase(),
    },
    {
      key: 'sport',
      title: t('Вид спорта'),
      width: '14%',
      cell: (row) => row.sport_type_name || <span className="t-note">{t('не указан')}</span>,
      sortBy: (row) => row.sport_type_name ?? null,
    },
    { key: 'level', title: t('Уровень'), width: '13%', cell: (row) => row.level_title || <span className="t-note">{t('не указан')}</span> },
    {
      key: 'date',
      title: t('Дата'),
      width: '11%',
      align: 'right',
      cell: (row) => (row.date ? <span className="num">{formatDate(row.date)}</span> : <span className="t-note">{t('без даты')}</span>),
      // сортируем по самой дате, а не по её русскому написанию:
      // «01.09.2026» и «10.02.2026» в алфавите стоят не в том порядке
      sortBy: (row) => row.date ?? null,
    },
    { key: 'result', title: t('Результат'), width: '11%', cell: (row) => row.result || <span className="t-note">{t('нет')}</span> },
    {
      // значимое для поступления: отмеченное видят в карточке все роли и CV
      key: 'card',
      title: t('В карточке'),
      width: '96px',
      cell: (row) => (
        <Switch
          checked={row.show_in_card}
          aria-label={t('Показывать в карточке ученика: {name}, {student}', { name: row.name, student: row.student_name })}
          disabled={rows.update.isPending}
          onCheckedChange={(checked) => rows.update.mutate({ id: row.id, show_in_card: checked })}
        />
      ),
      sortBy: (row) => (row.show_in_card ? 0 : 1),
    },
    {
      key: 'actions',
      title: '',
      width: '64px',
      align: 'right',
      cell: (row) => (
        <RowMenu>
          <RowMenuItem onClick={() => setEditing(row)}>{t('Изменить')}</RowMenuItem>
          <RowMenuSeparator />
          <RowMenuItem risk keepOpen>
            <DeleteButton
              inMenu
              model="students.Competition"
              id={row.id}
              path="/competitions/"
              invalidate={[['competitions'], ['student-rows'], ['dashboard']]}
            />
          </RowMenuItem>
        </RowMenu>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Соревнования')}
        actions={
          <Button
            onClick={() => {
              setPicked([])
              setProblem(null)
              setAdding(true)
            }}
          >
            {t('Добавить соревнование')}
          </Button>
        }
      />

      <ManualEntryNote />

      <div className="toolbar">
        <Input
          placeholder={t('Поиск по названию или результату')}
          aria-label={t('Поиск по соревнованиям')}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="toolbar__spacer" />
        <span className="muted">
          {counted(list.data?.count ?? 0, 'выступление|выступления|выступлений')}
        </span>
      </div>

      {list.isLoading && <Loading kind="table" />}
      {list.error && <ErrorNote error={list.error} />}

      {!list.isLoading && (
        <DataCard
          title={t('Все выступления школы')}
          count={table.length || undefined}
          note={table.length > 0 ? t('Строка на каждого участника') : undefined}
          empty={table.length === 0 && (search ? t('по этому поиску ничего нет — очистите поиск') : t('заведите первое соревнование — руками или файлом'))}
          emptyAction={
            <Button variant="secondary" size="sm" onClick={search ? () => setSearch('') : () => setAdding(true)}>
              {search ? t('Очистить поиск') : t('Добавить соревнование')}
            </Button>
          }
        >
          <DataTable columns={columns} rows={table} rowKey={(row) => row.id} />
        </DataCard>
      )}

      <EditDrawer open={adding} onClose={() => setAdding(false)} title={t('Новое соревнование')} sub={t('Отметьте всех, кто выступал — на каждого появится своя строка')}>
          <label className="rows__picker">
            <span className="rowform__label">{t('Участники')}</span>
            <div className="pickers">
              {(students.data?.results ?? []).map((row) => (
                <label key={row.id} className="pickers__item">
                  <Checkbox
                    checked={picked.includes(row.id)}
                    onCheckedChange={(on) =>
                      setPicked((prev) => (on ? [...prev, row.id] : prev.filter((id) => id !== row.id)))
                    }
                  />
                  <span>{row.full_name}</span>
                </label>
              ))}
            </div>
          </label>
          {problem && (
            <Chip tone="bad">
              {problem}
            </Chip>
          )}
          <RowForm
            fields={fields}
            busy={rows.create.isPending}
            submitLabel={t('Завести')}
            onCancel={() => setAdding(false)}
            onSubmit={(values) => {
              if (picked.length === 0) {
                setProblem(t('Отметьте хотя бы одного участника — соревнование без выступавших не нужно'))
                return
              }
              setProblem(null)
              const shared = body(values)
              // строка на каждого участника: окно закрывается только когда все
              // заведены; частичная ошибка называется по именам, окно остаётся (D63)
              void Promise.allSettled(picked.map((student) => rows.create.mutateAsync({ student, ...shared }))).then((results) => {
                const failed = results
                  .map((result, index) => (result.status === 'rejected' ? index : -1))
                  .filter((index) => index >= 0)
                if (failed.length === 0) {
                  setAdding(false)
                  return
                }
                const names = failed.map((index) => (students.data?.results ?? []).find((row) => row.id === picked[index])?.full_name ?? '').filter(Boolean)
                const reason = (results[failed[0]] as PromiseRejectedResult).reason
                setProblem(
                  `${t('Не заведено: {names}.', { names: names.join(', ') })} ${reason instanceof Error ? reason.message : ''}`.trim(),
                )
                setPicked(failed.map((index) => picked[index]))
              })
            }}
          />
      </EditDrawer>

      <EditDrawer open={editing !== null} onClose={() => setEditing(null)} title={t('Изменить выступление')} sub={editing?.student_name}>
        {editing && (
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
              show_in_card: editing.show_in_card,
            }}
            busy={rows.update.isPending}
            submitLabel={t('Сохранить')}
            onCancel={() => setEditing(null)}
            onSubmit={(values) => {
              rows.update.mutate({ id: editing.id, ...body(values) })
              setEditing(null)
            }}
          />
        )}
      </EditDrawer>
    </div>
  )
}
