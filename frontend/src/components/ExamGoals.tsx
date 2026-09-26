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
import { DataCard, EmptyNote } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { NativeSelectOption } from './ui/native-select'
import { SelectField } from './SelectField'
import EditDrawer from './EditDrawer'
import Field from './Field'
import { Row, Rows } from './patterns'
import '../screens/academics/academics.css'

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

/** Правка цели: балл, дата экзамена и регистрации — в правой панели. */
function GoalEditor({ row, onClose }: { row: ExamGoalRow; onClose: () => void }) {
  const { update } = useExamGoalRows()
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
      { onSuccess: onClose, onError: (error) => toast.error(error.message) },
    )
  return (
    <div className="acad__form">
      <Field label={t('Целевой балл')} name="target_score" value={draft.target_score} onChange={(value) => setDraft({ ...draft, target_score: value })} />
      <Field kind="date" label={t('Дата экзамена')} name="exam_date" value={draft.exam_date} onChange={(value) => setDraft({ ...draft, exam_date: value })} />
      <Field kind="date" label={t('Дата регистрации')} name="registration_date" value={draft.registration_date} onChange={(value) => setDraft({ ...draft, registration_date: value })} />
      <div className="acad__actions">
        <Button disabled={update.isPending} onClick={save}>
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </div>
  )
}

export default function ExamGoals() {
  const navigate = useNavigate()
  const goals = useExamGoals()
  const attention = useGoalsAttention()

  const rows = goals.data?.results ?? []
  const lists = attention.data
  const { remove } = useExamGoalRows()
  const [editing, setEditing] = useState<ExamGoalRow | null>(null)
  const dateWords = (value: string | null) => (value ? new Date(value).toLocaleDateString('ru') : t('нет'))

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

      <div className="card card-pad mt-4">
        <span className="eyebrow">{t('Все цели')}</span>
        <CreateGoalForm />
        {rows.length === 0 && (
          <EmptyNote what="целей пока нет" who="ставят ученики с портфолио, вы подтверждаете" />
        )}
        <Rows>
          {rows.map((row) => (
            <Row
              key={row.id}
              avatar={row.student_name}
              title={row.student_name}
              note={`${row.exam_name} · ${t('цель')} ${row.target_score ?? t('нет')} · ${t('экзамен')} ${dateWords(row.exam_date)} · ${t('регистрация')} ${dateWords(row.registration_date)}`}
              acts={
                <span className="acad__inline">
                  <Button variant="secondary" size="sm" onClick={() => setEditing(row)}>
                    {t('Изменить')}
                  </Button>
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
                </span>
              }
            />
          ))}
        </Rows>
      </div>

      <EditDrawer open={editing !== null} onClose={() => setEditing(null)} title={editing ? editing.student_name : ''} sub={editing?.exam_name}>
        {editing && <GoalEditor key={editing.id} row={editing} onClose={() => setEditing(null)} />}
      </EditDrawer>
    </div>
  )
}
