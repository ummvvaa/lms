/**
 * Учебные группы: завести, поправить и убрать. Реестр школы, ведёт администратор.
 *
 * Группа с учениками не удаляется молча: сервер считает, сколько их,
 * и говорит об этом в диалоге. Правка появилась в фазе 30 — до неё
 * опечатку в коде группы можно было исправить только через базу.
 *
 * С фазы 60 куратор группы — назначение с датой, а не текст: у группы
 * один действующий куратор, история назначений раскрывается строкой.
 * Текстового поля с именем куратора у группы больше нет (фаза 61).
 */
import { useState } from 'react'
import {
  useAssignCurator,
  useCreateStudyGroup,
  useCuratorAssignments,
  useCurators,
  useStudyGroups,
  useUpdateStudyGroup,
  type StudyGroupRow,
} from '../api/hooks'
import DeleteButton from './DeleteButton'
import RowForm from './RowForm'
import { SelectField } from './SelectField'
import { counted, DataCard, ErrorNote, Loading } from './ui'
import { t } from '../i18n'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Input } from './ui/input'
import RowMenu, { RowMenuItem, RowMenuSeparator } from './RowMenu'

const GROUP_FIELDS = [
  { name: 'code', label: 'Код группы', kind: 'text' as const, required: true, placeholder: '11A' },
  { name: 'grade', label: 'Класс', kind: 'number' as const, required: true },
]

const today = () => new Date().toISOString().slice(0, 10)
const dateOf = (value: string) => new Date(value).toLocaleDateString('ru')

/** Назначить или сменить куратора: кто и с какой даты. */
function AssignForm({ group, onDone }: { group: StudyGroupRow; onDone: () => void }) {
  const curators = useCurators()
  const assign = useAssignCurator()
  const [curator, setCurator] = useState('')
  const [since, setSince] = useState(today())
  const [error, setError] = useState<string | null>(null)
  const people = (curators.data?.results ?? []).filter((row) => row.is_active)

  return (
    <form
      className="rows__form"
      onSubmit={(e) => {
        e.preventDefault()
        setError(null)
        assign.mutate(
          { group: group.id, curator: Number(curator), since },
          {
            onSuccess: onDone,
            onError: (err) => setError(err instanceof Error ? err.message : 'Не удалось назначить'),
          },
        )
      }}
    >
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <SelectField
          aria-label={t('Куратор')}
          value={curator}
          onChange={(e) => setCurator(e.target.value)}
          required
        >
          <option value="">{t('— выберите куратора —')}</option>
          {people.map((row) => (
            <option key={row.id} value={String(row.id)}>
              {row.full_name || row.email}
            </option>
          ))}
        </SelectField>
        <Input
          type="date"
          aria-label={t('Действует с')}
          value={since}
          onChange={(e) => setSince(e.target.value)}
          required
        />
        <Button size="sm" type="submit" disabled={assign.isPending || !curator}>
          {group.curator_user ? t('Сменить') : t('Назначить')}
        </Button>
        <Button variant="outline" size="sm" type="button" onClick={onDone}>
          {t('Отмена')}
        </Button>
      </div>
      {people.length === 0 && (
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
          {t('Кураторов пока нет — заведите учётную запись с ролью «Куратор» выше.')}
        </p>
      )}
      {error && <Badge variant="risk">{error}</Badge>}
    </form>
  )
}

/** История назначений группы: кто вёл, с какого числа и по какое. */
function AssignmentHistory({ group }: { group: number }) {
  const history = useCuratorAssignments(group)
  if (history.isLoading) return <Loading kind="table" />
  const rows = history.data?.results ?? []
  if (rows.length === 0) return <p className="muted rows__empty">{t('Назначений ещё не было')}</p>
  return (
    <ul className="rows__list">
      {rows.map((row) => (
        <li key={row.id} className="rows__item">
          <div className="rows__body">
            <div>
              <span className="rows__label">{row.curator_name}</span>
              <span className="muted rows__note">
                {' '}
                · {t('с')} {dateOf(row.since)} {row.until ? `${t('по')} ${dateOf(row.until)}` : `· ${t('действует')}`}
                {row.created_by_name && ` · ${t('назначил')} ${row.created_by_name}`}
              </span>
            </div>
            {row.is_active && <Badge variant="ok">{t('действует')}</Badge>}
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function StudyGroups() {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [assigning, setAssigning] = useState<number | null>(null)
  const [history, setHistory] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const list = useStudyGroups()
  const create = useCreateStudyGroup()
  const update = useUpdateStudyGroup()
  const rows = list.data?.results ?? []

  return (
    <DataCard
      title={t('Учебные группы')}
      note={t('По ним раскладываются ученики и считаются дашборды; куратор — назначением с датой')}
      count={rows.length}
      right={
        <Button variant="outline" size="sm" onClick={() => setAdding(!adding)}>
          {adding ? t('Отмена') : t('Завести группу')}
        </Button>
      }
    >
      {adding && (
        <RowForm
          fields={GROUP_FIELDS}
          busy={create.isPending}
          submitLabel={t('Завести')}
          onCancel={() => setAdding(false)}
          onSubmit={(values) => {
            setError(null)
            create.mutate(
              { code: String(values.code ?? '').trim(), grade: Number(values.grade ?? 11) },
              {
                onSuccess: () => setAdding(false),
                onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось завести группу'),
              },
            )
          }}
        />
      )}

      {error && <ErrorNote error={new Error(error)} />}
      {list.isLoading && <Loading kind="table" />}

      {!list.isLoading && rows.length === 0 && !adding && (
        <p className="muted rows__empty">{t('Групп пока нет — заведите первую')}</p>
      )}

      <ul className="rows__list">
        {rows.map((row) => (
          <li key={row.id} className="rows__item">
            <div className="rows__body">
              <div>
                <span className="rows__label">{row.code}</span>
                <span className="muted rows__note">
                  {' '}
                  · {row.grade} {t('класс')} · {counted(row.students_count, ['ученик', 'ученика', 'учеников'])}
                  {row.curator_user &&
                    ` · ${t('куратор')} ${row.curator_user.full_name} ${t('с')} ${dateOf(row.curator_user.since)}`}
                  {!row.curator_user && ` · ${t('куратор не назначен')}`}
                </span>{' '}
              </div>
              <div className="rows__actions">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAssigning(assigning === row.id ? null : row.id)}
                >
                  {row.curator_user ? t('Сменить') : t('Назначить')}
                </Button>
                <RowMenu>
                  <RowMenuItem onClick={() => setEditing(editing === row.id ? null : row.id)}>
                    {t('Изменить')}
                  </RowMenuItem>
                  <RowMenuItem onClick={() => setHistory(history === row.id ? null : row.id)}>
                    {t('История назначений')}
                  </RowMenuItem>
                  <RowMenuSeparator />
                  <RowMenuItem risk keepOpen>
                    <DeleteButton
                      inMenu
                      model="students.StudyGroup"
                      id={row.id}
                      path="/groups/"
                      invalidate={[['groups'], ['students'], ['curators']]}
                    />
                  </RowMenuItem>
                </RowMenu>
              </div>
            </div>
            {assigning === row.id && <AssignForm group={row} onDone={() => setAssigning(null)} />}
            {history === row.id && <AssignmentHistory group={row.id} />}
            {editing === row.id && (
              <RowForm
                fields={GROUP_FIELDS}
                row={{ code: row.code, grade: row.grade }}
                busy={update.isPending}
                submitLabel={t('Сохранить')}
                onCancel={() => setEditing(null)}
                onSubmit={(values) => {
                  setError(null)
                  update.mutate(
                    {
                      id: row.id,
                      code: String(values.code ?? '').trim(),
                      grade: Number(values.grade ?? row.grade),
                    },
                    {
                      onSuccess: () => setEditing(null),
                      onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось сохранить'),
                    },
                  )
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </DataCard>
  )
}

/** Кураторы с их группами на сегодня — вторая карточка экрана «Пользователи». */
export function Curators() {
  const curators = useCurators()
  if (curators.isLoading) return <Loading kind="table" />
  if (curators.error) return <ErrorNote error={curators.error} />
  const rows = curators.data?.results ?? []
  const unassigned = curators.data?.unassigned ?? []

  return (
    <DataCard
      title={t('Кураторы')}
      note={t('Кто какие группы ведёт сегодня; учётная запись куратора заводится как обычный пользователь')}
      count={rows.length}
    >
      {rows.length === 0 && <p className="muted rows__empty">{t('Кураторов пока нет')}</p>}
      <ul className="rows__list">
        {rows.map((row) => (
          <li key={row.id} className={`rows__item${row.is_active ? '' : ' users__off'}`}>
            <div className="rows__body">
              <div>
                <span className="rows__label">{row.full_name || row.email}</span>
                <span className="muted rows__note">
                  {' '}
                  · {row.groups.length ? row.groups.map((g) => g.code).join(', ') : t('групп нет')}
                  {!row.is_active && ` · ${t('доступ отключён')}`}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>
      {unassigned.length > 0 && (
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
          {t('Без куратора:')} {unassigned.map((g) => g.code).join(', ')}
        </p>
      )}
    </DataCard>
  )
}
