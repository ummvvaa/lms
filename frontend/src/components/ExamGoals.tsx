/**
 * Цели по экзаменам у академического директора (фаза 39).
 *
 * Списки «у кого нет целей», «экзамен на неделе», «не зарегистрировался»
 * плюс таблица целей с правкой и удалением. Ставит цель ученик
 * предложением; здесь директор ведёт их руками.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useDirectoryEntries,
  useExamGoalRows,
  useExamGoals,
  useGoalsAttention,
  useStudents,
  type ExamGoalRow,
} from '../api/hooks'
import { t } from '../i18n'
import { DataCard } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { NativeSelectOption } from './ui/native-select'
import { SelectField } from './SelectField'

/** Заведение цели руками — обычно её предлагает ученик, но право директора
 *  без кнопки существовало бы только для программиста. */
function CreateGoalForm() {
  const { create } = useExamGoalRows()
  const students = useStudents({ page_size: 500 })
  const exams = useDirectoryEntries('exam-kinds')
  const [draft, setDraft] = useState({ student: '', exam: '', target_score: '', exam_date: '' })

  const submit = () => {
    if (!draft.student || !draft.exam) {
      toast.error(t('Выберите ученика и экзамен'))
      return
    }
    create.mutate(
      {
        student: Number(draft.student),
        exam: Number(draft.exam),
        target_score: draft.target_score || null,
        exam_date: draft.exam_date || null,
      },
      {
        onSuccess: () => setDraft({ student: '', exam: '', target_score: '', exam_date: '' }),
        onError: (error) => toast.error(error.message),
      },
    )
  }

  return (
    <div className="goals__create">
      <SelectField
        size="sm"
        value={draft.student}
        onChange={(e) => setDraft({ ...draft, student: e.target.value })}
        aria-label={t('Ученик')}
      >
        <NativeSelectOption value="">{t('Ученик')}</NativeSelectOption>
        {(students.data?.results ?? []).map((row) => (
          <NativeSelectOption key={row.id} value={String(row.id)}>
            {row.last_name} {row.first_name}
          </NativeSelectOption>
        ))}
      </SelectField>
      <SelectField
        size="sm"
        value={draft.exam}
        onChange={(e) => setDraft({ ...draft, exam: e.target.value })}
        aria-label={t('Экзамен')}
      >
        <NativeSelectOption value="">{t('Экзамен')}</NativeSelectOption>
        {(exams.data?.results ?? []).map((row) => (
          <NativeSelectOption key={row.id} value={String(row.id)}>
            {row.name}
          </NativeSelectOption>
        ))}
      </SelectField>
      <Input
        className="goals__input num"
        placeholder={t('Целевой балл')}
        value={draft.target_score}
        onChange={(e) => setDraft({ ...draft, target_score: e.target.value })}
        aria-label={t('Целевой балл')}
      />
      <Input
        className="goals__input"
        type="date"
        value={draft.exam_date}
        onChange={(e) => setDraft({ ...draft, exam_date: e.target.value })}
        aria-label={t('Дата экзамена')}
      />
      <Button size="sm" disabled={create.isPending} onClick={submit}>
        {t('Завести цель')}
      </Button>
    </div>
  )
}

function GoalRow({ row }: { row: ExamGoalRow }) {
  const { update, remove } = useExamGoalRows()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({
    target_score: row.target_score ?? '',
    exam_date: row.exam_date ?? '',
    registration_date: row.registration_date ?? '',
  })

  const save = () =>
    update.mutate(
      {
        id: row.id,
        target_score: draft.target_score || null,
        exam_date: draft.exam_date || null,
        registration_date: draft.registration_date || null,
      },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => toast.error(error.message),
      },
    )

  return (
    <tr>
      <td>{row.student_name}</td>
      <td>{row.exam_name}</td>
      {editing ? (
        <>
          <td>
            <Input
              className="goals__input num"
              value={draft.target_score}
              onChange={(e) => setDraft({ ...draft, target_score: e.target.value })}
              aria-label={t('Целевой балл')}
            />
          </td>
          <td>
            <Input
              className="goals__input"
              type="date"
              value={draft.exam_date}
              onChange={(e) => setDraft({ ...draft, exam_date: e.target.value })}
              aria-label={t('Дата экзамена')}
            />
          </td>
          <td>
            <Input
              className="goals__input"
              type="date"
              value={draft.registration_date}
              onChange={(e) => setDraft({ ...draft, registration_date: e.target.value })}
              aria-label={t('Дата регистрации')}
            />
          </td>
          <td>
            <Button size="sm" disabled={update.isPending} onClick={save}>
              {t('Сохранить')}
            </Button>
          </td>
        </>
      ) : (
        <>
          <td className="num">{row.target_score ?? '—'}</td>
          <td>{row.exam_date ? new Date(row.exam_date).toLocaleDateString('ru') : '—'}</td>
          <td>{row.registration_date ? new Date(row.registration_date).toLocaleDateString('ru') : '—'}</td>
          <td>
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {t('Изменить')}
            </Button>{' '}
            <Button
              variant="ghost"
              size="sm"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(row.id, {
                  onSuccess: () => toast.success(t('Цель в архиве')),
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Убрать')}
            </Button>
          </td>
        </>
      )}
    </tr>
  )
}

export default function ExamGoals() {
  const navigate = useNavigate()
  const goals = useExamGoals()
  const attention = useGoalsAttention()

  const rows = goals.data?.results ?? []
  const lists = attention.data

  return (
    <div>
      <div className="grid grid--two">
        <DataCard
          title={t('Целей пока нет')}
          note={t('Ученики, у которых не поставлено ни одной цели')}
          count={lists?.no_goals.length ?? 0}
          accent="warn"
        >
          <ul className="rows__list">
            {(lists?.no_goals ?? []).slice(0, 10).map((row) => (
              <li key={row.id} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{row.name}</span>
                </div>
                <Button variant="outline" size="sm" onClick={() => navigate(`/students/${row.id}`)}>
                  {t('Открыть')}
                </Button>
              </li>
            ))}
          </ul>
        </DataCard>

        <DataCard
          title={t('Экзамен на неделе')}
          note={t('До экзамена меньше семи дней')}
          count={lists?.exam_this_week.length ?? 0}
          accent="teal"
        >
          <ul className="rows__list">
            {(lists?.exam_this_week ?? []).map((row, index) => (
              <li key={index} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{row.name}</span>
                  <span className="muted rows__note">
                    {row.exam} · {row.date ? new Date(row.date).toLocaleDateString('ru') : ''}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </DataCard>

        <DataCard
          title={t('Нет даты регистрации')}
          note={t('Экзамен близко, а дата регистрации не отмечена')}
          count={lists?.not_registered.length ?? 0}
          accent="risk"
        >
          <ul className="rows__list">
            {(lists?.not_registered ?? []).map((row, index) => (
              <li key={index} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{row.name}</span>
                  <span className="muted rows__note">
                    {row.exam} · {row.date ? new Date(row.date).toLocaleDateString('ru') : ''}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </DataCard>
      </div>

      <div className="card card-pad" style={{ marginTop: 16 }}>
        <span className="eyebrow">{t('Все цели')}</span>
        <CreateGoalForm />
        {rows.length === 0 && (
          <p className="muted">{t('Целей пока нет — ученики ставят их с портфолио, вы подтверждаете.')}</p>
        )}
        {rows.length > 0 && (
          <table className="history">
            <thead>
              <tr>
                <th>{t('Ученик')}</th>
                <th>{t('Экзамен')}</th>
                <th>{t('Цель')}</th>
                <th>{t('Дата экзамена')}</th>
                <th>{t('Регистрация')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <GoalRow key={row.id} row={row} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
