/**
 * Учебные группы: завести, поправить и убрать. Реестр школы, ведёт администратор.
 *
 * Группа с учениками не удаляется молча: сервер считает, сколько их,
 * и говорит об этом в диалоге. Правка появилась в фазе 30 — до неё
 * опечатку в коде группы можно было исправить только через базу.
 */
import { useState } from 'react'
import { useCreateStudyGroup, useStudyGroups, useUpdateStudyGroup } from '../api/hooks'
import DeleteButton from './DeleteButton'
import RowForm from './RowForm'
import { counted, DataCard, ErrorNote, Loading } from './ui'
import { t } from '../i18n'

const GROUP_FIELDS = [
  { name: 'code', label: 'Код группы', kind: 'text' as const, required: true, placeholder: '11A' },
  { name: 'grade', label: 'Класс', kind: 'number' as const, required: true },
  { name: 'curator', label: 'Куратор', kind: 'text' as const },
]

export default function StudyGroups() {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const list = useStudyGroups()
  const create = useCreateStudyGroup()
  const update = useUpdateStudyGroup()
  const rows = list.data?.results ?? []

  return (
    <DataCard
      title={t('Учебные группы')}
      note={t('По ним раскладываются ученики и считаются дашборды')}
      count={rows.length}
      right={
        <button className="btn btn-ghost btn-sm" onClick={() => setAdding(!adding)}>
          {adding ? t('Отмена') : t('Завести группу')}
        </button>
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
              {
                code: String(values.code ?? '').trim(),
                grade: Number(values.grade ?? 11),
                curator: String(values.curator ?? ''),
              },
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
                  · {row.grade} класс · {counted(row.students_count, ['ученик', 'ученика', 'учеников'])}
                  {row.curator && ` · куратор ${row.curator}`}
                </span>
              </div>
              <div className="rows__actions">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setEditing(editing === row.id ? null : row.id)}
                >
                  {editing === row.id ? t('Закрыть') : t('Изменить')}
                </button>
                <DeleteButton
                  model="students.StudyGroup"
                  id={row.id}
                  path="/groups/"
                  invalidate={[['groups'], ['students']]}
                />
              </div>
            </div>
            {editing === row.id && (
              <RowForm
                fields={GROUP_FIELDS}
                row={{ code: row.code, grade: row.grade, curator: row.curator }}
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
                      curator: String(values.curator ?? ''),
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
